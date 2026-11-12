//! Einen offenen Deskriptor ueber einen Unix-Socket weiterreichen
//! (`SCM_RIGHTS`).
//!
//! **Warum das existiert** (DESIGN, Regel „Jedes Werkzeug bekommt nur seine
//! Rechte", Abschnitt „Fernausfuehrung"): Der einzige Netznutzer ist das
//! Gateway. Fuer `ssh` oeffnet es die TCP-Verbindung und reicht den offenen
//! Socket an den Ausfuehrer weiter — **als Deskriptor, nicht als Adresse**.
//! Der Ausfuehrer hat kein Netz (`IPAddressDeny=any`); `ssh` kann deshalb
//! keine zweite Verbindung aufbauen, auch wenn es wollte. Der Kernel ist der
//! Riegel, nicht eine Zeile Programmcode.
//!
//! **Kein Deskriptor auf Vorrat:** Es wird genau die Liste weitergereicht,
//! die der Aufrufer uebergibt. Der Empfaenger bekommt nur Deskriptoren, die
//! ihm jemand ausdruecklich schickt; ein leeres Feld heisst „keine Rechte".
//!
//! Die Deskriptoren kommen **ohne** `MSG_CMSG_CLOEXEC` an und werden vom
//! Aufrufer ausdruecklich auf die Nummer gelegt, die `ssh` erwartet. Wer sie
//! nicht braucht, muss sie schliessen — sonst haelt der Prozess den Socket
//! offen, bis er endet.

use std::io;
use std::os::unix::io::{AsRawFd, RawFd};
use std::os::unix::net::UnixStream;

/// Eine Zeile plus Deskriptoren schicken.
///
/// `fds` leer ist der normale Weg (nur Daten). Dann verhaelt sich die
/// Funktion wie ein `write`.
pub fn senden(strom: &UnixStream, daten: &[u8], fds: &[RawFd]) -> io::Result<()> {
    if daten.is_empty() {
        return Ok(());
    }
    // Sicherheitsnetz: mehr Deskriptoren als das Betriebssystem je Nachricht
    // zulaesst, waere ein Fehler des Aufrufers -- und still abgeschnitten
    // noch schlimmer. SCM_MAX_FD ist 253 auf Linux.
    if fds.len() > 253 {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "zu viele Deskriptoren in einer Nachricht"));
    }
    let iov = libc::iovec { iov_base: daten.as_ptr() as *mut libc::c_void, iov_len: daten.len() };
    let mut kopf: libc::msghdr = unsafe { std::mem::zeroed() };
    kopf.msg_iov = &iov as *const libc::iovec as *mut libc::iovec;
    kopf.msg_iovlen = 1;
    // Platz fuer cmsghdr + Rechte + Auffuellen auf 8 Byte.
    let mut cmsg_puffer = [0u8; 64];
    if !fds.is_empty() {
        kopf.msg_control = cmsg_puffer.as_mut_ptr() as *mut libc::c_void;
        // cmsg_len/msg_controllen sind je nach libc u32 (musl) oder usize
        // (glibc); gerechnet wird in u32, verglichen in usize.
        let bytes = (fds.len() * std::mem::size_of::<RawFd>()) as u32;
        let platz = unsafe { libc::CMSG_SPACE(bytes) };
        kopf.msg_controllen = platz as _;
        if platz as usize > cmsg_puffer.len() {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "zu viele Deskriptoren fuer den Puffer"));
        }
        unsafe {
            let cmsg = libc::CMSG_FIRSTHDR(&kopf);
            (*cmsg).cmsg_level = libc::SOL_SOCKET;
            (*cmsg).cmsg_type = libc::SCM_RIGHTS;
            (*cmsg).cmsg_len = libc::CMSG_LEN(bytes) as _;
            std::ptr::copy_nonoverlapping(fds.as_ptr() as *const u8, libc::CMSG_DATA(cmsg), fds.len() * std::mem::size_of::<RawFd>());
        }
    }
    loop {
        let n = unsafe { libc::sendmsg(strom.as_raw_fd(), &kopf, 0) };
        if n >= 0 {
            if n as usize == daten.len() {
                return Ok(());
            }
            // Teilschreiben heisst: der restliche Teil kaeme ohne Rechte an.
            // Lieber ein Fehler als eine halbe Nachricht.
            return Err(io::Error::new(io::ErrorKind::WriteZero, "Nachricht nur teilweise geschrieben"));
        }
        let e = io::Error::last_os_error();
        if e.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        return Err(e);
    }
}

/// Eine Nachricht samt moeglichen Deskriptoren lesen.
///
/// Gibt die gelesenen Bytes und die Deskriptoren zurueck. **Die Deskriptoren
/// gehoeren dem Aufrufer** und muessen geschlossen werden.
pub fn empfangen(strom: &UnixStream, max: usize) -> io::Result<(Vec<u8>, Vec<RawFd>)> {
    let mut puffer = vec![0u8; max];
    let iov = libc::iovec { iov_base: puffer.as_mut_ptr() as *mut libc::c_void, iov_len: puffer.len() };
    // Platz fuer 8 Deskriptoren -- mehr schickt keine unserer Stellen.
    let mut cmsg_puffer = [0u8; 128];
    let mut kopf: libc::msghdr = unsafe { std::mem::zeroed() };
    kopf.msg_iov = &iov as *const libc::iovec as *mut libc::iovec;
    kopf.msg_iovlen = 1;
    kopf.msg_control = cmsg_puffer.as_mut_ptr() as *mut libc::c_void;
    kopf.msg_controllen = cmsg_puffer.len() as _;

    let n = loop {
        let n = unsafe { libc::recvmsg(strom.as_raw_fd(), &mut kopf, 0) };
        if n >= 0 {
            break n as usize;
        }
        let e = io::Error::last_os_error();
        if e.kind() == io::ErrorKind::Interrupted {
            continue;
        }
        return Err(e);
    };
    puffer.truncate(n);
    let mut fds = Vec::new();
    unsafe {
        let mut cmsg = libc::CMSG_FIRSTHDR(&kopf);
        while !cmsg.is_null() {
            if (*cmsg).cmsg_level == libc::SOL_SOCKET && (*cmsg).cmsg_type == libc::SCM_RIGHTS {
                let kopf_bytes = libc::CMSG_LEN(0) as usize;
                let laenge = ((*cmsg).cmsg_len as usize).saturating_sub(kopf_bytes);
                let groesse = std::mem::size_of::<RawFd>();
                let anzahl = laenge / groesse;
                let daten = libc::CMSG_DATA(cmsg);
                for i in 0..anzahl {
                    let mut fd: RawFd = -1;
                    std::ptr::copy_nonoverlapping(daten.add(i * groesse), &mut fd as *mut RawFd as *mut u8, groesse);
                    fds.push(fd);
                }
            }
            cmsg = libc::CMSG_NXTHDR(&kopf, cmsg);
        }
    }
    Ok((puffer, fds))
}

/// Einen Deskriptor schliessen, ohne sich um Fehler zu kuemmern (beim
/// Aufraeumen nach einer abgelehnten Anfrage).
pub fn schliessen(fd: RawFd) {
    if fd >= 0 {
        unsafe {
            libc::close(fd);
        }
    }
}

/// `fd` so legen, dass das Kind es unter der gewuenschten Nummer erbt:
/// `dup2` auf `ziel` und das Schliessen-beim-Start (`FD_CLOEXEC`) loeschen.
pub fn erben_lassen(fd: RawFd, ziel: RawFd) -> io::Result<RawFd> {
    if fd == ziel {
        // Schon die richtige Nummer -- nur das CLOEXEC muss weg.
    } else {
        let r = unsafe { libc::dup2(fd, ziel) };
        if r < 0 {
            return Err(io::Error::last_os_error());
        }
        // Das Original ist jetzt ein zweites Handle auf denselben Socket.
        schliessen(fd);
    }
    let flags = unsafe { libc::fcntl(ziel, libc::F_GETFD) };
    if flags < 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { libc::fcntl(ziel, libc::F_SETFD, flags & !libc::FD_CLOEXEC) } < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(ziel)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::os::unix::io::FromRawFd;
    use std::os::unix::net::UnixStream;

    /// Zwei verbundene Sockets wie Gateway und Ausfuehrer.
    fn paar() -> (UnixStream, UnixStream) {
        UnixStream::pair().unwrap()
    }

    #[test]
    fn ein_deskriptor_kommt_mit_der_nachricht_an() {
        let (a, b) = paar();
        // Ein rohr-aehnliches Ziel: ein zweiter Socket-Paar-Ende als "Netz".
        let (ziel, gegen) = paar();
        senden(&a, b"{\"op\":\"ssh\"}\n", &[ziel.as_raw_fd()]).unwrap();
        let (daten, fds) = empfangen(&b, 1024).unwrap();
        assert_eq!(daten, b"{\"op\":\"ssh\"}\n");
        assert_eq!(fds.len(), 1);
        // Der weitergegebene Deskriptor zeigt auf dieselbe Verbindung.
        let mut hin = std::mem::ManuallyDrop::new(unsafe { UnixStream::from_raw_fd(fds[0]) });
        hin.write_all(b"hallo").unwrap();
        let mut puffer = [0u8; 5];
        let mut g = gegen;
        g.read_exact(&mut puffer).unwrap();
        assert_eq!(&puffer, b"hallo");
        drop(std::mem::ManuallyDrop::into_inner(hin));
    }

    #[test]
    fn ohne_rechte_kommen_keine_an() {
        let (a, b) = paar();
        senden(&a, b"x\n", &[]).unwrap();
        let (daten, fds) = empfangen(&b, 64).unwrap();
        assert_eq!(daten, b"x\n");
        assert!(fds.is_empty());
    }

    #[test]
    fn zwei_deskriptoren_kommen_beide_an() {
        let (a, b) = paar();
        let (e1, _g1) = paar();
        let (e2, _g2) = paar();
        senden(&a, b"y\n", &[e1.as_raw_fd(), e2.as_raw_fd()]).unwrap();
        let (_, fds) = empfangen(&b, 64).unwrap();
        assert_eq!(fds.len(), 2);
        for fd in fds {
            schliessen(fd);
        }
    }

    #[test]
    fn erben_lassen_legt_die_nummer_und_loescht_cloexec() {
        // Eine Nummer, die in diesem Prozess frei ist: die Tests laufen
        // nebeneinander, und ein festes `9` gehoert mal einem Socketpair
        // eines anderen Tests -- dann schloesse `dup2` dessen Verbindung
        // (am 12.11. genau so passiert).
        let ziel: RawFd = (100..200).find(|n| unsafe { libc::fcntl(*n, libc::F_GETFD) } < 0).expect("freie Nummer");
        // Ein roher Deskriptor, den kein Rust-Typ besitzt: `erben_lassen`
        // schliesst das Original, und ein UnixStream-Destructor wuerde
        // dieselbe Nummer ein zweites Mal schliessen (IO-Safety-Abbruch).
        let roh = unsafe { libc::dup(0) };
        assert!(roh >= 0);
        let neu = erben_lassen(roh, ziel).unwrap();
        assert_eq!(neu, ziel);
        let flags = unsafe { libc::fcntl(ziel, libc::F_GETFD) };
        assert_eq!(flags & libc::FD_CLOEXEC, 0);
        // Auf "das Original ist zu" wird hier **nicht** geprueft: die Tests
        // laufen in einem Prozess nebeneinander, und nach dem Schliessen kann
        // ein anderer Faden dieselbe Nummer bekommen -- die Probe maesse dann
        // dessen Deskriptor (am 12.11. genau so passiert). Dass `dup2`
        // schliesst, ist Betriebssystem-Zusage, nicht unsere.
        schliessen(ziel);
    }
}
