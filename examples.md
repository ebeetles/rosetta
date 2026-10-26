# Examples

Real output from the default build: 2,000 chengyu and 2,000 English idioms, embedded with the `bge-m3` + `multilingual-e5-large` ensemble. Numbers are cosine distances, where lower is closer. They come from `python -m rosetta equiv …` and friends. The web UI shows the same results.

## Where it works

### 1. 易如反掌 → piece of cake

"As easy as turning over your palm" and "piece of cake" share no words and no imagery. Meaning search puts them first, and the rest of the list is useful too.

```
易如反掌 (yì rú fǎn zhǎng): 比喻事情非常容易做。
  1. piece of cake           0.15  something easy to do.
  2. It's a cinch            0.17  It's a very easy task.
  3. sail through something  0.17  to go through something very quickly and easily.
  4. an open book            0.19  [of someone or something] easy to understand.
  5. downhill all the way    0.21  easy the entire way.
```

It works in reverse as well: `equiv piece of cake` returns 易如反掌 (0.15), then 一蹴而就 (0.21).

### 2. 班门弄斧 → teach one's grandmother to suck eggs

"Swinging an axe at the master carpenter Lu Ban's door" lands on the English idiom about lecturing an expert, at rank 1.

```
  1. teach one's grandmother to suck eggs   0.24  to try to tell or show someone more knowledgeable or experienced than oneself…
```

### 3. 火上浇油 → fan the flames, add fuel to the fire

Both English fire idioms tie for first at 0.13. "Pouring oil on a fire" carries over almost word for word.

### 4. 守口如瓶 → keep one's mouth shut

The Phase 3 pair ("my lips are sealed") misses, but every one of the top five is a real equivalent:

```
  1. play one's cards close to one's chest   0.18
  2. keep one's mouth shut                   0.18
  3. keep something under one's hat          0.19
  4. not breathe a word                      0.19
  5. hush something up                       0.20
```

The miss is about the eval list, not the search. "My lips are sealed" is glossed as a first-person promise ("I will tell no one this secret"), while 守口如瓶 describes a person.

### 5. carry coals to Newcastle → 多此一举, 画蛇添足

Starting from English, "doing something redundant" finds both Chinese idioms for pointless extra effort:

```
  1. 多此一举  0.17  指多余的，没有必要的举动。
  2. 画蛇添足  0.20  比喻做了多余的事，非但无益，反而不合适。
```

This is also why 画蛇添足 misses its Phase 3 partner, "gild the lily": the dictionary defines "gild the lily" as *adding ornament* to something fine, and "carry coals to Newcastle" is the better match for *doing something unnecessary*.

### 6. Describing a situation, in Chinese

`find "说话谨慎，不泄露秘密"` ("speak carefully, don't leak secrets"):

```
  1. 守口如瓶            zh  0.10
  2. 门无杂宾            zh  0.16
  3. 谨言慎行            zh  0.16
  4. 隔墙有耳            zh  0.17   ← "walls have ears", a neighbor, not a synonym
  5. Keep your mouth shut  en  0.20
```

### 7. Add, then search

In one running session, `add` 杯水车薪 ("a cup of water on a burning cart of firewood"), then `equiv 杯水车薪`:

```
  1. a drop in the bucket  0.28
```

The new idiom is searchable immediately, with no rebuild.

## The literal-vs-meaning contrast

### 8. compare 画蛇添足

```
  by its words              by its meaning
  画龙点睛   0.20           多此一举   0.11
  打草惊蛇   0.22           附赘县疣   0.11
  虎头蛇尾   0.23           楚才晋用   0.15
  雪上加霜   0.24           数米量柴   0.15
  揠苗助长   0.24           无的放矢   0.15
  add insult to injury 0.26 鼠穴寻羊   0.16
```

By its words, its neighbors share 画 (draw) or 蛇 (snake). By its meaning, they're about superfluous or useless effort, led by 多此一举, its closest synonym. One embedding of the four characters even reaches across languages to "add insult to injury", probably on the strength of 添 (add).

## Instructive failures

### 9. False friend: 过河拆桥 vs. "burn one's bridges"

Both are about bridges, and both are about burning (or tearing down) your way back. But 过河拆桥 means discarding the people who helped you, and "burn one's bridges" means cutting off your own retreat. The search keeps them apart: "burn one's bridges" isn't in the top 50. It finds the real equivalent instead:

```
  2. bite the hand that feeds one   0.24  to do harm to someone who does good things for you.
```

The near-miss happens on the *other* side. 破釜沉舟 ("break the pots, sink the boats") really is "burn one's bridges" in its no-retreat sense. But McGraw-Hill's figurative sense of the phrase is the social one ("to act unpleasantly in a situation that you are leaving"), so the pair misses. Rosetta finds "cross the Rubicon" (0.19) instead, which is arguably better.

### 10. False friend: 亡羊补牢 vs. "too little, too late"

亡羊补牢 says it's *not* too late to fix things after a loss. The search returns repair idioms ("get the kinks out", "patch something up", "pick up the pieces") and correctly ranks "too little, too late" nowhere near the top. That's the right call, but the results also drop the hopeful "never too late" nuance. `explain` is there to put it back.

### 11. The funny miss: 九牛一毛 → "by the dozens"

"One hair from nine oxen" means a negligible amount. Its top English match is "by the dozens": *many*. Both glosses are about quantity in a big-number frame (极大数量 / "large, indefinite number"), and the embeddings weigh the topic over the polarity. "A drop in the bucket" comes in sixth (0.28).

### 12. When the words are the meaning: compare "gild the lily"

For English, the literal column is mostly noise: "the glad hand", "lay it on the line", "hold the line". They share *the* and a few letters (*line*, *limelight*), not ideas. English idioms are short and full of function words, so their surface forms carry very little signal.
