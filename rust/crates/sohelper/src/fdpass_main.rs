//! `chimera-fdpass` — holt die offene Verbindung beim Ausführer ab und reicht
//! sie an `ssh` zurück.
//!
//! **Warum es das braucht** (DESIGN, „Fernausführung"): `ssh` soll eine
//! Verbindung benutzen, die es **nicht selbst geöffnet** hat. Mit
//! `ProxyUseFdpass=yes` startet `ssh` den `ProxyCommand` und gibt ihm einen
//! Socketpair auf **stdin**; über diesen schickt der Proxy den fertigen
//! Deskriptor zurück (`SCM_RIGHTS`, dazu mindestens ein Byte — `ssh` bricht
//! sonst mit „expected received 1 got 0" ab). Danach spricht `ssh` über genau
//! diese Verbindung.
//!
//! **Warum der Umweg über einen Unix-Socket** (gemessen 12.11.2026, OpenSSH
//! 9.9): `ssh` schließt im Proxy-Kind **alle** Deskriptoren ab 3 — ein
//! geerbtes `fd 3` ist dort nicht mehr offen („Deskriptor 3 ist nicht
//! offen"). Der einzige Kanal, den `ssh` dem Proxy garantiert, ist stdin.
//! Also holt dieses Programm die Verbindung beim Ausführer ab (Unix-Socket,
//! `SCM_RIGHTS`) und gibt sie auf stdin an `ssh` weiter. Die Annahme, der
//! Proxy gebe eine Zeile `fd <n>` auf stdout aus, trifft für
//! `ProxyUseFdpass` **nicht** zu.
//!
//! Das Programm öffnet nichts und verbindet nichts — es reicht weiter, was
//! ihm der Ausführer gibt.
//!
//! Aufruf: `chimera-fdpass <socketpfad>` (stdin = Socketpair von ssh)

use std::os::unix::io::RawFd;

/// Ein Byte Inhalt — `ssh` verwirft es und will nur, dass die Nachricht
/// nicht leer ist.
const INHALT: u8 = b'f';

fn melde(text: &str) {
    eprintln!("chimera-fdpass: {text}");
}

/// Einen Deskriptor über einen Socket schicken (derselbe Weg wie im
/// Gateway, nur in die andere Richtung).
fn schicken(ziel: RawFd, nummer: RawFd) -> Result<(), String> {
    let iov = libc::iovec { iov_base: &INHALT as *const u8 as *mut libc::c_void, iov_len: 1 };
    let mut puffer = [0u8; 64];
    let mut kopf: libc::msghdr = unsafe { std::mem::zeroed() };
    kopf.msg_iov = &iov as *const libc::iovec as *mut libc::iovec;
    kopf.msg_iovlen = 1 as _;
    kopf.msg_control = puffer.as_mut_ptr() as *mut libc::c_void;
    let bytes = std::mem::size_of::<RawFd>() as u32;
    let platz = unsafe { libc::CMSG_SPACE(bytes) };
    kopf.msg_controllen = platz as _;
    if platz as usize > puffer.len() {
        return Err("Puffer zu klein fuer die Nachricht".into());
    }
    unsafe {
        let cmsg = libc::CMSG_FIRSTHDR(&kopf);
        (*cmsg).cmsg_level = libc::SOL_SOCKET;
        (*cmsg).cmsg_type = libc::SCM_RIGHTS;
        (*cmsg).cmsg_len = libc::CMSG_LEN(bytes) as _;
        std::ptr::copy_nonoverlapping(&nummer as *const RawFd as *const u8, libc::CMSG_DATA(cmsg), bytes as usize);
    }
    let n = unsafe { libc::sendmsg(ziel, &kopf, 0) };
    if n < 0 {
        return Err(format!("sendmsg: {}", std::io::Error::last_os_error()));
    }
    Ok(())
}

fn main() {
    let arg = std::env::args().nth(1).unwrap_or_default();
    if arg == "--version" || arg == "-V" {
        println!("chimera-fdpass {}", gemein::version());
        return;
    }
    if arg.is_empty() {
        melde("Aufruf ist 'chimera-fdpass <socketpfad>'");
        std::process::exit(2);
    }
    // 1. Die Verbindung beim Ausführer abholen.
    let strom = match std::os::unix::net::UnixStream::connect(&arg) {
        Ok(s) => s,
        Err(e) => {
            melde(&format!("Übergabe-Socket {arg} nicht erreichbar: {e}"));
            std::process::exit(1);
        }
    };
    let _ = strom.set_read_timeout(Some(std::time::Duration::from_secs(30)));
    let anfrage = [0u8; 1];
    use std::io::Write;
    if let Err(e) = (&strom).write_all(&anfrage) {
        // Ein Byte als Weckruf; der Ausführer antwortet mit dem Deskriptor.
        melde(&format!("Weckruf nicht geschrieben: {e}"));
        std::process::exit(1);
    }
    let mut puffer = [0u8; 8];
    let iov = libc::iovec { iov_base: puffer.as_mut_ptr() as *mut libc::c_void, iov_len: puffer.len() };
    let mut cmsg_puffer = [0u8; 64];
    let mut kopf: libc::msghdr = unsafe { std::mem::zeroed() };
    kopf.msg_iov = &iov as *const libc::iovec as *mut libc::iovec;
    kopf.msg_iovlen = 1 as _;
    kopf.msg_control = cmsg_puffer.as_mut_ptr() as *mut libc::c_void;
    kopf.msg_controllen = cmsg_puffer.len() as _;
    use std::os::unix::io::AsRawFd;
    let n = unsafe { libc::recvmsg(strom.as_raw_fd(), &mut kopf, 0) };
    if n <= 0 {
        melde(&format!("keine Verbindung vom Ausführer bekommen ({})", std::io::Error::last_os_error()));
        std::process::exit(1);
    }
    let mut nummer: RawFd = -1;
    unsafe {
        let mut cmsg = libc::CMSG_FIRSTHDR(&kopf);
        while !cmsg.is_null() {
            if (*cmsg).cmsg_level == libc::SOL_SOCKET && (*cmsg).cmsg_type == libc::SCM_RIGHTS {
                std::ptr::copy_nonoverlapping(
                    libc::CMSG_DATA(cmsg),
                    &mut nummer as *mut RawFd as *mut u8,
                    std::mem::size_of::<RawFd>(),
                );
            }
            cmsg = libc::CMSG_NXTHDR(&kopf, cmsg);
        }
    }
    if nummer < 0 {
        melde("der Ausführer hat keinen Deskriptor mitgeschickt");
        std::process::exit(1);
    }
    // 2. Sie an ssh zurückreichen: stdin (0) ist der Socketpair von ssh.
    if unsafe { libc::fcntl(0, libc::F_GETFD) } < 0 {
        melde("stdin ist geschlossen — ssh gibt dem Proxy einen Socketpair");
        std::process::exit(1);
    }
    if let Err(e) = schicken(0, nummer) {
        melde(&e);
        std::process::exit(1);
    }
}
