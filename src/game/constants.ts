/* 世界常量：与后端 REALM_TABLE 保持一致（前端仅做展示） */

export const REALMS = [
  "炼气一层", "炼气二层", "炼气三层", "炼气四层", "炼气五层",
  "炼气六层", "炼气七层", "炼气八层", "炼气九层", "筑基初期",
];

export const EXP_MAX = [100, 130, 170, 260, 330, 400, 580, 680, 800, 9999];

export const INIT_STATE = {
  realm_index: 0, hp: 100, hp_max: 100, qi: 50, qi_max: 50,
  exp: 10, spirit_stones: 30,
  items: [
    { name: "回气丹", qty: 2, rarity: "下品" },
    { name: "师父的钝剑", qty: 1, rarity: "下品" },
  ],
  memory: ["独守青牛山破庙三年，师父云游未归", "昨夜炼气入体，初入炼气一层"],
  recent: [], turn: 0,
};

export const OPENING =
  "庆元十七年，秋。\n\n青牛山下的破庙里，你睁开眼。师父走了三年，留下半袋米、一柄钝剑，" +
  "和一句\"灵根如此，好自为之\"。昨夜，你终于炼气入体。\n\n山外妖兽近年频繁出没，坊市灵石价格一日三涨，" +
  "传闻北边荒泽又现秘境。米缸将尽——是时候下山了。";

export const INIT_CHOICES = [
  { id: "A", text: "下山，赶往青牛镇", risk: "mid", tag: "explore" },
  { id: "B", text: "在破庙再打坐半日，巩固境界", risk: "low", tag: "cultivate" },
  { id: "C", text: "翻检师父遗物，看看还有何可用", risk: "low", tag: "explore" },
] as const;
