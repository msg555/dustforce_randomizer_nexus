#include "data.h"

const string DOOR_ENTITY = "level_door";

const int KEYBOARD_MARGIN = 20;
const int KEYBOARD_HEIGHT_PER_ROW = 100;

class keyboard_key {
  keyboard_key() {
  }

  keyboard_key(string txt, int row, int col, int width=1, int height=1) {
    this.txt = txt;
    this.row = row;
    this.col = col;
    this.width = width;
    this.height = height;

    float rp = row + height / 2.0;
    float cp = col + width / 2.0;
    cnt_x = KEYBOARD_MARGIN + (cp / 16.0) * (1600 - KEYBOARD_MARGIN * 2) + cp;
    cnt_y = 900 - KEYBOARD_MARGIN - 4 * KEYBOARD_HEIGHT_PER_ROW + rp * KEYBOARD_HEIGHT_PER_ROW;
    x1 = cnt_x - (1600 - KEYBOARD_MARGIN * 2) * width / 16.0 / 2;
    y1 = cnt_y - KEYBOARD_HEIGHT_PER_ROW * height / 2.0;
    x2 = cnt_x + (1600 - KEYBOARD_MARGIN * 2) * width / 16.0 / 2;
    y2 = cnt_y + KEYBOARD_HEIGHT_PER_ROW * height / 2.0;
  }

  string txt;
  int row;
  int col;
  int width;
  int height;

  float cnt_x;
  float cnt_y;
  float x1, x2, y1, y2;
};

class script {
  scene@ g;
  nexus_api@ n;

  bool first_frame;
  dictionary level_index;

  array<int> added_entities;

  [hidden] string seed;
  [hidden] array<string> level_mapping;

  string seed_text;
  uint key_index;
  int x_int_last;
  int y_int_last;
  bool mouse_pressed;
  array<keyboard_key> keys;

  script() {
    first_frame = true;
    for (uint i = 0; i < LEVELS.size(); i++) {
      level_index["" + LEVELS[i]] = i;
    }

    srand(timestamp_now());
    @g = get_scene();
    @n = get_nexus_api();
    setup_keyboard();
  }

  void setup_keyboard() {
    array<string> alphas = {
      "QWERTYUIOP",
      "ASDFGHJKL",
      "ZXCVBNM",
    };

    key_index = 0;
    x_int_last = 0;
    y_int_last = 0;
    for (uint i = 0; i < alphas.size(); i++) {
      for (uint j = 0; j < alphas[i].size(); j++) {
        keys.insertLast(keyboard_key(alphas[i].substr(j, 1), i, j));
      }
    }
    keys.insertLast(keyboard_key("1", 0, 10));
    keys.insertLast(keyboard_key("2", 0, 11));
    keys.insertLast(keyboard_key("3", 0, 12));
    keys.insertLast(keyboard_key("4", 1, 10));
    keys.insertLast(keyboard_key("5", 1, 11));
    keys.insertLast(keyboard_key("6", 1, 12));
    keys.insertLast(keyboard_key("7", 2, 10));
    keys.insertLast(keyboard_key("8", 2, 11));
    keys.insertLast(keyboard_key("9", 2, 12));
    keys.insertLast(keyboard_key("0", 3, 10));
    keys.insertLast(keyboard_key("clear", 0, 13, 3));
    keys.insertLast(keyboard_key("back", 1, 13, 3));
    keys.insertLast(keyboard_key("rand", 2, 13, 3));
    keys.insertLast(keyboard_key("enter", 3, 13, 3));
  }

  void setup_levels() {
    if (level_mapping.size() != 0) {
      /* Use stored mapping rather than recompute. This also ensures
       * existing rolls of the nexus don't change when the level list
       * is updated. */
      return;
    }

    // seed based on text
    int64 sd = 555;
    for (uint i = 0; i < seed.size(); i++) {
      sd = (sd * 100000007 + seed[i]) % 1000000007;
    }
    puts("text seed: " + seed);
    puts("real seed: " + sd);
    srand(sd);

    array<uint> indexes;
    level_mapping.resize(0);
    for (uint i = 0; i < LEVELS.size(); i++) {
      indexes.insertLast(i);
      level_mapping.insertLast("");
    }
    for (uint i = indexes.size(); i < CUSTOMS.size(); i++) {
      if (rand() / 1073741823.0 > 1.0 * indexes.size() / (i + 1)) {
        continue;
      }
      indexes[rand() % indexes.size()] = i;
    }

    for (uint i = 0; i < indexes.size(); i++) {
      for (uint j = i + 1; j < indexes.size(); j++) {
        if (indexes[j] < indexes[i]) {
          uint tmp = indexes[i];
          indexes[i] = indexes[j];
          indexes[j] = tmp;
        }
      }
    }

    for (uint i = 0; i < LEVELS.size(); i += 16) {
      array<uint> pos = {0, 0, 0, 0};
      for (int j = 0; j < 16; j++) {
        const level_data@ lvl = @CUSTOMS[indexes[i + j]];

        array<int> tset = {0, 1, 2, 3};
        for (uint si = 0; ; si++) {
          for (uint sj = si + 1; sj < 4; sj++) {
            if (lvl.tiles[tset[si]] < lvl.tiles[tset[sj]]) {
              uint tmp = tset[si];
              tset[si] = tset[sj];
              tset[sj] = tmp;
            }
          }
          if (pos[tset[si]] < 4) {
            level_mapping[16 * tset[si] + i / 4 + pos[tset[si]]++] = lvl.level;
            break;
          }
        }
      }
    }
  }

  void on_level_start() {
    if (seed != "") {
      setup_levels();
      fixup_scores();
    }
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
          puts("Update score for " + level);
          n.score_set(level, thorough, finesse, time, expected_key_type);
        }
      }
    }
  }

  void process_entity_load(entity@ e) {
    uint ind = uint(level_index["" + e.id()]);

    // Verify the door is an OG door
    if (e.type_name() != "level_door") {
      return;
    }
    varstruct@ vars = @e.vars();
    string og_level = vars.get_var("file_name").get_string();
    for (uint i = 0; i < og_level.size(); i++) {
      if (og_level[i] == 0x2D) {
        return;
      }
    }

    entity@ e_new = create_entity("level_door");
    e_new.x(e.x());
    e_new.y(e.y());
    e_new.layer(e.layer());

    varstruct@ vars_new = @e_new.vars();
    vars_new.get_var("file_name").set_string(level_mapping[ind]);
    vars_new.get_var("door_set").set_int32(
      vars.get_var("door_set").get_int32()
    );

    g.add_entity(@e_new);
    g.remove_entity(@e);

    if (authors.exists(level_mapping[ind])) {
      author_placard ap(string(authors[level_mapping[ind]]));
      entity@ e_placard = create_scripttrigger(@ap).as_entity();
      e_placard.x(e.x());
      e_placard.y(e.y());
      g.add_entity(@e_placard);
    }
  }

  void editor_step() {
    seed = "";
    level_mapping.resize(0);
  }

  void step(int) {
    if (seed == "") {
      step_keyboard();
    } else {
      step_door_replacement();
    }
  }

  void step_keyboard() {
    controllable@ p = controller_controllable(0);
    int x_int = p.x_intent();
    int y_int = p.y_intent();

    int k_r = keys[key_index].row;
    int k_c = keys[key_index].col;
    if (x_int == x_int_last) {
      x_int = 0;
    } else {
      x_int_last = x_int;
    }
    if (y_int == y_int_last) {
      y_int = 0;
    } else {
      y_int_last = y_int;
    }

    if (x_int != 0 || y_int != 0) {
      bool found = false;
      while (!found) {
        k_r = (k_r + y_int + 4) % 4;
        k_c = (k_c + x_int + 16) % 16;
        for (uint i = 0; i < keys.size(); i++) {
          if (keys[i].row == k_r && keys[i].col == k_c) {
            found = true;
            key_index = i;
          }
        }
      }
    }

    bool add_key = false;
    if ((g.mouse_state(0) & 4) != 0) {
      // Left clicked
      if (!mouse_pressed) {
        int mouse_x = int(g.mouse_x_hud(0)) + 800;
        int mouse_y = int(g.mouse_y_hud(0)) + 450;

        for (uint i = 0; i < keys.size(); i++) {
          keyboard_key@ k = @keys[i];
          if (k.x1 < mouse_x && mouse_x < k.x2 && k.y1 < mouse_y && mouse_y < k.y2) {
            key_index = i;
          }
        }
        add_key = true;
      }
      mouse_pressed = true;
    } else {
      mouse_pressed = false;
    }

    if (add_key || p.jump_intent() != 0) {
      keyboard_key@ k = @keys[key_index];
      if (k.txt == "clear") {
        seed_text = "";
      } else if (k.txt == "back") {
        if (seed_text.size() > 0) {
          seed_text.resize(seed_text.size() - 1);
        }
      } else if (k.txt == "rand") {
        seed_text = "" + (rand() % 100000);
      } else if (k.txt == "enter") {
        if (seed_text != "") {
          seed = seed_text;
          setup_levels();
          fixup_scores();
        }
      } else if (seed_text.size() < 10)  {
        seed_text += k.txt;
      }
    }

    p.x_intent(0);
    p.y_intent(0);
    p.taunt_intent(0);
    p.heavy_intent(0);
    p.light_intent(0);
    p.dash_intent(0);
    p.jump_intent(0);
    p.fall_intent(0);
  }

  void step_door_replacement() {
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

  void draw(float sub_frame) {
    if (seed == "") {
      draw_keyboard();
      return;
    }
  }

  void draw_keyboard() {
    canvas@ c = create_canvas(true, 12, 2);
    c.translate(-800, -450);
    c.draw_rectangle(0, 0, 1600, 900, 0, 0xFF222222);

    textfield@ txt = create_textfield();
    txt.colour(0xFFFFFFFF);
    txt.align_horizontal(0);
    txt.align_vertical(0);

    txt.text(seed_text);
    txt.set_font("Caracteres", 140);
    c.draw_text(@txt, 800, 300, 1, 1, 0);

    txt.set_font("Caracteres", 72);
    txt.text("Set nexus seed");
    c.draw_text(@txt, 800, 100, 1, 1, 0);

    for (uint i = 0; i < keys.size(); i++) {
      keyboard_key@ k = @keys[i];
      txt.text(k.txt);

      if (i == key_index) {
        c.draw_rectangle(k.x1, k.y1, k.x2, k.y2, 0, 0xFF555555);
      }
      c.draw_text(@txt, k.cnt_x, k.cnt_y, 1, 1, 0);
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
    txt.text(s.seed + (is_ngplus ? "*" : ""));
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
