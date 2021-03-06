class level_data {
  level_data() {
  }

  level_data(string level, int tile_forest, int tile_mansion, int tile_city,
             int tile_lab, int tile_virtual, float difficulty) {
    this.level = level;
    this.tiles.insertLast(tile_forest);
    this.tiles.insertLast(tile_mansion);
    this.tiles.insertLast(tile_city);
    this.tiles.insertLast(tile_lab);
    this.tiles.insertLast(tile_virtual);
    this.difficulty = difficulty;
  }

  string level;
  array<int> tiles;
  float difficulty;
};

/* Use customs_lite.h for faster compilation during development. */
// #include "customs_lite.h"
#include "customs.h"

#include "authors.h"

const array<int> LEVELS = {
  1627, // downhill
  1629, // shadedgrove
  1640, // dahlia
  1644, // fields
  1631, // momentum
  1639, // fireflyforest
  1642, // tunnels
  1645, // momentum2
  1646, // suntemple
  1649, // ascent
  1650, // summit
  1651, // grasscave
  1652, // den
  1653, // autumnforest
  1647, // garden
  1648, // hyperdifficult
  1657, // atrium
  1655, // secretpassage
  1659, // alcoves
  1660, // mezzanine
  1663, // cave
  1661, // cliffsidecaves
  1665, // library
  1666, // courtyard
  1668, // precarious
  1671, // treasureroom
  1670, // arena
  1673, // ramparts
  1676, // moontemple
  1681, // observatory
  1680, // parapets
  1679, // brimstone
  1684, // vacantlot
  1685, // sprawl
  1686, // development
  1687, // abandoned
  1688, // park
  1690, // boxes
  1694, // chemworld
  1692, // factory
  1701, // tunnel
  1702, // basement
  1697, // scaffold
  1700, // cityrun
  1703, // clocktower
  1704, // concretetemple
  1705, // alley
  1706, // hideout
  1708, // control
  1709, // ferrofluid
  1710, // titan
  1711, // satellite
  1712, // vat
  1714, // venom
  1716, // security
  1715, // mary
  1717, // wiringfixed
  1720, // containment
  1719, // orb
  1723, // pod
  1726, // mary2
  1724, // coretemple
  1730, // abyss
  1728, // dome
};
