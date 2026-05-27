use std::{
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc::{self, Sender},
        Arc,
    },
    thread,
    time::Duration,
};

use tauri::AppHandle;

#[derive(Clone, Debug)]
pub struct AttentionEvent {
    pub source: String,
}

#[derive(Clone)]
pub struct AttentionBroker {
    sender: Sender<AttentionEvent>,
}

impl AttentionBroker {
    pub fn spawn(
        app: AppHandle,
        on_attention: fn(&AppHandle, AttentionEvent),
    ) -> Self {
        let (sender, receiver) = mpsc::channel::<AttentionEvent>();

        thread::spawn(move || {
            while let Ok(event) = receiver.recv() {
                let app_handle_for_callback = app.clone();

                let _ = app.run_on_main_thread(move || {
                    on_attention(&app_handle_for_callback, event);
                });
            }
        });

        Self { sender }
    }

    pub fn source(&self, source: impl Into<String>) -> AttentionSourceHandle {
        AttentionSourceHandle {
            source: source.into(),
            broker: self.clone(),
            latest_ticket: Arc::new(AtomicU64::new(0)),
        }
    }

    fn emit_event(&self, event: AttentionEvent) {
        let _ = self.sender.send(event);
    }
}

#[derive(Clone)]
pub struct AttentionSourceHandle {
    source: String,
    broker: AttentionBroker,
    latest_ticket: Arc<AtomicU64>,
}

impl AttentionSourceHandle {
    #[cfg(debug_assertions)]
    pub fn emit(&self) {
        self.broker.emit_event(AttentionEvent {
            source: self.source.clone(),
        });
    }

    pub fn schedule_latest(&self, delay: Duration) {
        let ticket = self.latest_ticket.fetch_add(1, Ordering::Relaxed) + 1;
        let source = self.source.clone();
        let broker = self.broker.clone();
        let latest_ticket = self.latest_ticket.clone();

        thread::spawn(move || {
            thread::sleep(delay);

            if latest_ticket.load(Ordering::Relaxed) == ticket {
                broker.emit_event(AttentionEvent { source });
            }
        });
    }
}