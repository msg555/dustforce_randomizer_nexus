#include "data.h"

const string DOOR_ENTITY = "level_door";

class script {
  scene@ g;
  nexus_api@ n;

  bool first_frame;
  dictionary level_index;
  array<int> added_entities;

  [hidden] string seed_name;
  [hidden] string full_seed_name;
  [hidden] array<string> level_mapping;
  [hidden] array<string> authors;

  script() {
    first_frame = true;
    for (uint i = 0; i < LEVELS.size(); i++) {
      level_index["" + LEVELS[i]] = i;
    }

    @g = get_scene();
    @n = get_nexus_api();
  }

  void on_level_start() {
    fixup_scores();
  }

  void fixup_scores() {
    for (uint i = 0; i < level_mapping.size(); i++) {
      string level = level_mapping[i];

      int thorough;
      int finesse;
      float time;
      int key_type;
      if (n.score_lookup(level, thorough, finesse, time, key_type)) {
        int expected_key_type = (i % 16) / 4;
        if (expected_key_type == 0) {
          expected_key_type = 4;
        }

        if (key_type != expected_key_type) {
          n.score_set(level, thorough, finesse, time, expected_key_type);
        }
      }
    }
  }

  void process_entity_load(entity@ e) {
    // Verify the door is an OG door
    if (e.type_name() != "level_door") {
      return;
    }

    varstruct@ vars = @e.vars();
    string og_level = vars.get_var("file_name").get_string();
    if (og_level != "") {
      return;
    }

    entity@ e_new = create_entity("level_door");
    e_new.x(e.x());
    e_new.y(e.y());
    e_new.layer(e.layer());

    varstruct@ vars_new = @e_new.vars();
    uint ind = uint(level_index["" + e.id()]);
    vars_new.get_var("file_name").set_string(level_mapping[ind]);
    vars_new.get_var("door_set").set_int32(
      vars.get_var("door_set").get_int32()
    );

    g.remove_entity(@e);
    g.add_entity(@e_new);

    author_placard ap(authors[ind]);
    entity@ e_placard = create_scripttrigger(@ap).as_entity();
    e_placard.x(e.x());
    e_placard.y(e.y());
    g.add_entity(@e_placard);
  }

  void checkpoint_load() {
    first_frame = true;
  }

  void step(int) {
    for (uint i = 0; i < added_entities.size(); i++) {
      process_entity_load(entity_by_id(added_entities[i]));
    }
    added_entities.resize(0);

    if (!first_frame) {
      return;
    }
    first_frame = false;

    for (uint i = 0; i < LEVELS.size(); i++) {
      entity@ e = entity_by_id(LEVELS[i]);
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

class toggle_layer : trigger_base {
  scene@ g;

  [text] int layer;
  [check] bool show;

  toggle_layer() {
    @g = get_scene();
    layer = 18;
    show = false;
  }

  void activate(controllable@ e) {
    g.layer_visible(layer, show);
  }
}

class seed_display : trigger_base {
  scene@ g;
  script@ s;
  scripttrigger@ self;

  textfield@ txt;

  [text] int layer;
  [text] int sub_layer;
  [colour] uint colour;

  bool check_ngplus;
  bool is_ngplus;

  seed_display() {
    @g = get_scene();
    @txt = create_textfield();

    layer = 20;
    sub_layer = 3;
    colour = 0xFFFFFFFF;

    txt.colour(0xFFFFFFFF);
    txt.align_horizontal(0);
    txt.align_vertical(0);
  }

  void init(script@ s, scripttrigger@ self) {
    @this.s = @s;
    @this.self = @self;
  }

  void step() {
    if (check_ngplus) {
      return;
    }
    check_ngplus = true;

    int jnk;
    s.n.get_keys_used(jnk, jnk, jnk, jnk, is_ngplus);
  }

  void editor_draw(float) {
    txt.colour(colour);
    txt.text("0123456789");
    txt.draw_world(layer, sub_layer, self.x(), self.y(), 0.8, 0.8, 0);
  }

  void draw(float) {
    txt.colour(colour);
    txt.text(s.seed_name + (is_ngplus ? "*" : ""));
    txt.draw_world(layer, sub_layer, self.x(), self.y(), 0.8, 0.8, 0);
  }
}

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
