# Idiom Rosetta

Match Chinese and English idioms by what they mean, not what they say.

![compare 画蛇添足 in the web UI](docs/compare.jpg)

## What it does and why I chose it

Idiom Rosetta is able to find idioms in both Chinese and English, given a description of it. For example, if we said something like "getting multiple things done with only one action", the top responses will be "Killing two birds with one stone" in English, and "一举两得" (“one act, two gains”) in Chinese. It can also find equivalent idioms between the two languages, as well as full explanations of what each idiom means. I chose this because there is no way to do something like this with simple keyword searches. Idioms are beautiful in the sense that most times, it is unclear what they mean if you just take it in the literal sense, therefore it must be broken down to its meaning before being searched with a vector database.

## What's in the database

- **Sources:** Chinese chengyu from the [chinese-xinhua](https://github.com/pwxcoo/chinese-xinhua) dataset (30,895 entries), and English idioms from the [`englishidioms`](https://pypi.org/project/englishidioms/) package, which bundles 21,866 entries parsed from the *McGraw-Hill Dictionary of American Idioms and Phrasal Verbs*.
- **One item = one idiom:** the idiom itself plus its dictionary meaning. Nothing is chunked, but entries are trimmed. For Chinese, I keep only the figurative part of the explanation, because Xinhua explanations usually start by describing the literal picture. For English, I keep only the sense marked `Fig.` (figurative), cut off at the first example sentence. I drop one- and two-word entries (mostly phrasal verbs) and keep only one of several variants that share a definition.
- **How many:** 2,000 Chinese and 2,000 English idioms (4,000 items), sampled with a fixed seed. A short list of test and showcase idioms is always included. Each item is stored twice, in two collections with the same id: `literal` embeds the idiom's own words, and `meaning` embeds its definition. That's 8,000 vectors.
- **Metadata on each item:** `lang` (`zh`/`en`), `idiom`, `meaning`, `example`, `source` (`xinhua`, `mcgraw-hill`, or `user`), `pinyin`, and `key`, a normalized form used for lookups. Chinese items also carry `meaning_pinyin`, plus `idiom_en` (the literal picture in English) and `meaning_en` (the meaning in English), both translated by Claude. These are display-only and aren't embedded, so they don't affect search.

## How to add and search

**Adding:** in the shell, type `add` and answer the prompts: idiom, language, meaning, and an optional example and pinyin. In the web UI, use the **Add an idiom** tab. Before saving, Rosetta embeds the new meaning and shows the three closest existing ones. If the idiom is already stored, or a meaning is nearly identical (cosine distance below 0.1), it asks before saving. Saved idioms go into both collections and show up in the very next search, with no rebuild. If you look up an idiom that isn't stored, it offers to add it.

**Searching:** there are four ways to search, each a tab in the web UI and a command in the shell.
- `find "<description>"` describes a situation in either language and gets idioms from both. `--lang zh` or `--lang en` narrows it to one.
- `equiv <idiom>` gives the closest idioms in the other language.
- `compare <idiom>` shows two columns: neighbors by the idiom's words vs. by its meaning.
- `explain <idiom>` sends the equivalents to Claude, which says which fits best and how the others differ in tone or usage.

## Two test queries, and why keyword search would miss them

**Query 1: `find "trying to speed things up only makes them worse" --lang zh`**

| # | Idiom | Literally | Meaning | Distance |
| --- | --- | --- | --- | --- |
| 1 | 欲速反迟 | wanting speed, one is instead slow | being overly impatient for quick results only delays reaching one's goal; more haste, less speed | 0.25 |
| 2 | 挖肉补疮 | cut out flesh to patch a sore | to resort to harmful measures to meet an immediate need, heedless of the future | 0.26 |
| 3 | 揠苗助长 | pull up seedlings to help them grow | to violate the natural course of things in one's eagerness for quick results, only to spoil everything | 0.27 |

A keyword search finds nothing here. The query is English, and the stored Chinese idioms and their meanings are in Chinese, so none of the stored Chinese entries contains any query word. A translation dictionary wouldn't help much either: 揠苗助长's words are about seedlings, which the query never mentions. The embedding models place the English description and the Chinese explanation near each other because they mean the same thing.

**Query 2: `equiv carry coals to Newcastle`**

| # | Idiom | Literally | Meaning | Distance |
| --- | --- | --- | --- | --- |
| 1 | 多此一举 | one move too many | a superfluous, unnecessary action | 0.17 |
| 2 | 画蛇添足 | draw a snake and add feet | to do something superfluous that, far from helping, makes things worse | 0.20 |
| 3 | 附赘县疣 | an attached growth, a hanging wart | superfluous, useless things | 0.22 |

The query and its matches share no words, no imagery, and no language: coal and Newcastle versus snakes, feet, and warts. Even translating word by word wouldn't connect them. The only thing they have in common is the idea of doing something redundant, and that's what the meaning collection captures. The `compare` command shows the contrast directly: searched by its own words, 画蛇添足's neighbors are other snake idioms (打草惊蛇, 虎头蛇尾). Searched by its meaning, they're idioms about pointless extra effort.

## How I used AI

I used Claude chat to brainstorm ideas and settle on this final idea. Then I worked with the same chat to produce a comprehensive spec doc including all the features I wanted as well as the steps to get there. Finally I worked with Claude code to incrementally build the project and add/tweak features towards the end.

## Citations

- Chinese idioms: [pwxcoo/chinese-xinhua](https://github.com/pwxcoo/chinese-xinhua), MIT license.
- English idioms: [`englishidioms`](https://pypi.org/project/englishidioms/) by Mahmoud Zaghloul, parsed from the *McGraw-Hill Dictionary of American Idioms and Phrasal Verbs* (Richard A. Spears, McGraw-Hill). The dictionary text is copyrighted and the package allows personal, non-commercial use, so the data is installed locally and never committed to this repo.
- Chen et al., "BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation," arXiv:2402.03216, 2024 (`BAAI/bge-m3`, MIT license).
- Wang et al., "Multilingual E5 Text Embeddings: A Technical Report," arXiv:2402.05672, 2024 (`intfloat/multilingual-e5-large`, MIT license).
- [Chroma](https://www.trychroma.com/), [sentence-transformers](https://www.sbert.net/), [pypinyin](https://github.com/mozillazg/python-pinyin) (MIT), and the [Anthropic API](https://docs.anthropic.com/) (Claude Opus 5.5).
- Fonts from Google Fonts: Ma Shan Zheng, Noto Serif SC, Noto Sans SC, Newsreader, Hanken Grotesk, IBM Plex Mono.

---