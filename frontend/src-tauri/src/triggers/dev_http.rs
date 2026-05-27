use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
};

use crate::attention::AttentionSourceHandle;

pub const SOURCE: &str = "trigger.dev-cli";
const PORT: u16 = 7878;

/// Spawns a minimal HTTP server on localhost that fires an attention event on
/// every request — useful for testing while the window is hidden.
///
/// Usage (from any terminal while `tauri dev` is running):
///   Invoke-WebRequest http://127.0.0.1:7878   # PowerShell
///   curl http://127.0.0.1:7878                # curl
///
/// Only compiled and started in debug builds (`cargo tauri dev`).
/// Never present in production releases.
pub fn spawn(handle: AttentionSourceHandle) {
    thread::spawn(move || {
        let listener = match TcpListener::bind(("127.0.0.1", PORT)) {
            Ok(l) => l,
            Err(e) => {
                eprintln!("[dev] attention trigger server failed to bind on port {PORT}: {e}");
                return;
            }
        };

        println!("[dev] attention trigger server listening on http://127.0.0.1:{PORT}");

        for stream in listener.incoming() {
            let Ok(mut stream) = stream else {
                continue;
            };

            let mut buf = [0u8; 512];
            let _ = stream.read(&mut buf);

            let response =
                "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok";
            let _ = stream.write_all(response.as_bytes());

            handle.emit();
        }
    });
}
