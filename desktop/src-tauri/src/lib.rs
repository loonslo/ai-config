use std::path::Path;
use std::sync::Mutex;
use tauri::{Emitter, Manager, State};

#[derive(Default)]
struct PendingOpenPackage(Mutex<Option<String>>);

#[tauri::command]
fn take_open_package(state: State<'_, PendingOpenPackage>) -> Option<String> {
  state.0.lock().ok().and_then(|mut pending| pending.take())
}

fn package_argument(args: &[String]) -> Option<String> {
  args.iter()
    .find(|argument| Path::new(argument).extension().is_some_and(|extension| extension.eq_ignore_ascii_case("zip")))
    .cloned()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
      if let Some(path) = package_argument(&args) {
        if let Some(state) = app.try_state::<PendingOpenPackage>() {
          if let Ok(mut pending) = state.0.lock() {
            *pending = Some(path);
          }
        }
        let _ = app.emit("package-opened", ());
      }
    }))
    .manage(PendingOpenPackage::default())
    .invoke_handler(tauri::generate_handler![take_open_package])
    .setup(|app| {
      let arguments = std::env::args().skip(1).collect::<Vec<_>>();
      if let Some(path) = package_argument(&arguments) {
        if let Ok(mut pending) = app.state::<PendingOpenPackage>().0.lock() {
          *pending = Some(path);
        }
      }
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while building tauri application");
}
