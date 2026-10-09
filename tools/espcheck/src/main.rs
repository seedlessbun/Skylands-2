use esplugin::{GameId, ParseOptions, Plugin};
use std::path::Path;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut p = Plugin::new(GameId::SkyrimSE, Path::new(&args[1]));
    match p.parse_file(ParseOptions::whole_plugin()) {
        Ok(()) => {
            println!("parsed OK");
            println!("masters: {:?}", p.masters().unwrap());
            println!("is_light_plugin: {:?}", p.is_light_plugin());
            println!("is_valid_as_light_plugin: {:?}", p.is_valid_as_light_plugin());
            
            println!("record_and_group_count: {:?}", p.record_and_group_count());
        }
        Err(e) => { println!("PARSE ERROR: {e}"); std::process::exit(1); }
    }
}
