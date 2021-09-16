const string DOOR_ENTITY = "level_door";

class level_info {
  level_info() {
    key_get = 4;
  }

  [entity,label:'Door',tooltip:'Door ID'] int door_id;
  [option,0:Wood,1:Silver,2:Gold,3:Red,4:None] int key_get;
  [text,label:'Author'] string author;

  // Used by randomizer to override level/door sprite without having
  // to write into the region data of the level file. Should not
  // be needed generally since you can just edit these attributes
  // on the door entity directly.
  [hidden] string level;
  [hidden] int door_sprite;
  [hidden] string display_name;
}

class script {
  scene@ g;
  nexus_api@ n;

  bool first_frame;
  dictionary level_index;
  array<int> added_entities;

  [label:'Levels'] array<level_info> levels;

  script() {
    first_frame = true;
    @g = get_scene();
    @n = get_nexus_api();
  }

  void on_level_start() {
    init_data();
    fixup_scores();
  }

  void init_data() {
    for (uint i = 0; i < levels.size(); i++) {
      level_index["" + levels[i].door_id] = i;
    }
  }

  void fixup_scores() {
    for (uint i = 0; i < levels.size(); i++) {
      level_info@ info = @levels[i];

      int thorough;
      int finesse;
      float time;
      int key_type;
      if (n.score_lookup(info.level, thorough, finesse, time, key_type)) {
        int expected_key_type = info.key_get;
        if (expected_key_type == 0) {
          expected_key_type = 4;
        } else if (expected_key_type == 4) {
          expected_key_type = 0;
        }

        if (key_type != expected_key_type) {
          n.score_set(info.level, thorough, finesse, time, expected_key_type);
        }
      }
    }
  }

  void process_entity_load(entity@ e) {
    // Verify the door is an OG door
    if (e.type_name() != "level_door") {
      return;
    }

    level_info@ info = @levels[uint(level_index["" + e.id()])];

    /* Get original door vars */
    varstruct@ vars = @e.vars();
    string og_level = vars.get_var("file_name").get_string();
    int og_door_sprite = vars.get_var("door_set").get_int32();
    string og_display_name = vars.get_var("display_name").get_string();

    /* Update any omitted vars to match the actual value */
    if (info.level == "") {
      info.level = og_level;
    }
    if (info.door_sprite == 0) {
      info.door_sprite = og_door_sprite;
    }
    if (info.display_name == "") {
      info.display_name = og_display_name;
    }

    /* Add the author placard if needed */
    if (info.author != "") {
      author_placard ap(info.author);
      entity@ e_placard = create_scripttrigger(@ap).as_entity();
      e_placard.x(e.x());
      e_placard.y(e.y());
      g.add_entity(@e_placard);

      /* Clear author so we don't create it again */
      info.author = "";
    }

    /* Check if we can skip the door update */
    if (info.level == og_level &&
        info.door_sprite == og_door_sprite &&
        info.display_name == og_display_name) {
      return;
    }

    /* Replace original door with new door */
    entity@ e_new = create_entity("level_door");
    e_new.x(e.x());
    e_new.y(e.y());
    e_new.layer(e.layer());

    varstruct@ vars_new = @e_new.vars();
    vars_new.get_var("file_name").set_string(info.level);
    vars_new.get_var("door_set").set_int32(info.door_sprite);
    vars_new.get_var("display_name").set_string(info.display_name);

    g.remove_entity(@e);
    g.add_entity(@e_new);
  }

  void checkpoint_load() {
    first_frame = true;
  }

  void step(int) {
    for (uint i = 0; i < added_entities.size(); i++) {
      entity@ e = entity_by_id(added_entities[i]);
      if (@e != null) {
        process_entity_load(@e);
      }
    }
    added_entities.resize(0);

    if (!first_frame) {
      return;
    }
    first_frame = false;

    for (uint i = 0; i < levels.size(); i++) {
      entity@ e = entity_by_id(levels[i].door_id);
      if (@e != null) {
        process_entity_load(@e);
      }
    }
  }

  void entity_on_add(entity@ e) {
    if (level_index.exists("" + e.id())) {
      added_entities.insertLast(e.id());
    }
  }
};

class author_placard : trigger_base {
  scene@ g;
  script@ s;
  scripttrigger@ self;
  canvas@ cvs;

  textfield@ txt;

  [hidden] string author;

  author_placard() {
  }

  author_placard(string author) {
    this.author = author;
  }

  void init(script@ s, scripttrigger@ self) {
    @this.s = @s;
    @this.self = @self;
    @txt = create_textfield();
    @cvs = create_canvas(false, 21, 22);
    txt.set_font("Caracteres", 36);
    txt.text(author);
    txt.colour(0xFFFFFFFF);
    txt.align_horizontal(0);
    txt.align_vertical(0);
  }

  void draw(float) {
    cvs.reset();
    cvs.translate(self.x(), 48 * round(self.y() / 48.0) + 10);
    cvs.scale(0.5, 0.5);
    cvs.draw_text(@txt, 0, 0, 1, 1, 0);
  }
}
