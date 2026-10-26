# Prompt log: Idiom Rosetta

> ✏️ **Note to self, delete before submitting.** The prompts in the code blocks are copied verbatim from my Claude Code session, typos included; don't edit them. Everything marked ✏️ is a draft or a gap for me to rewrite or fill in. The "What happened" notes were drafted by Claude from the session and need to be checked and put in my own words. Some messages were sent by clicking a suggested-reply button in the app rather than typed. Those are labelled, and the button text is quoted as sent.

## Tools and models


- **Planning:** [How I wrote the project spec, "Idiom Rosetta — Project Spec.md": by hand, or with which AI tool, and how much time it took.]
- **Building:** Claude Code in the Claude desktop app (Code tab), running **Claude Opus 5.5**. It wrote and ran the code, the data experiments, and the tests, and used its built-in browser to check the web UI. I used it because it can run commands and test in a real browser, so I could debug step by step instead of copying code back and forth. Two Claude Code skills were loaded during the session: **frontend-design**, which I asked for in my first prompt, for the web UI, and **claude-api**, for the Anthropic SDK code.
- **Inside the app:** the app calls **Claude Opus 5.5** through the Anthropic API for `explain` and to translate the 2,000 Chinese idioms into English. Search uses two local embedding models, `BAAI/bge-m3` and `intfloat/multilingual-e5-large`; these aren't chat assistants.
- [Any other tools: ChatGPT, Copilot, etc., if used.]

## Session log

### 1. Kickoff: spec, clarifying questions, then build

I worked with Claude chat for the spec doc in this chat: https://claude.ai/share/8b7149db-2468-47a5-adf5-217d5036c93f

```text
@"/Users/elwinli/Downloads/Idiom Rosetta — Project Spec.md"
I want you to first read through the project spec attached, ask me any clarifying questions if there are any. Once everything is clear, start implementation, make sure to use the frontend design skill for the UI, it shouldnt look blank
```

Claude asked three multiple-choice questions (paraphrased below; my answers are exact):

- *The spec says CLI-only, but you mentioned a UI. What should the UI be?* → picked **"CLI + web front end (Recommended)"**
- *Which LLM should `explain` use?* → picked **"Anthropic Claude"** instead of the spec's OpenAI
- *Where should the project live?* → typed my own answer:

```text
Heres the repo https://github.com/ebeetles/rosetta.git
```

- **Data:** cleaned 2,000 Chinese and 2,000 English idioms. Two problems turned up while inspecting the raw data:
  - Xinhua explanations start with the literal picture ("画蛇时给蛇添上脚。比喻…"), so cleaning keeps only the figurative part from 比喻 onward. Otherwise the literal words would leak into the meaning embeddings.
  - Two English test idioms from my spec aren't in the dataset, so they were swapped for close ones.
- **Database:** built two Chroma collections, `literal` and `meaning`.
- **The Phase 3 quality gate failed:** the spec's model scored **3/10** on my test pairs. Following the spec's fallback plan, Claude compared six embedding models. The best single models reached 5/10, and combining `bge-m3` with `e5-large` reached 7/10 (6/10 on the final data). That ensemble became the default.
- **A data fix:** `compare 画蛇添足` showed only one snake idiom in the "by its words" column, because random sampling had dropped the others. A small showcase list of famous idioms is now always included.
- **A server crash:** the web UI's first load returned HTTP 500 because two requests created the Chroma client at once. It was fixed with a lock and a warm-up at startup.
- **UI review:** further fixes came from reviewing screenshots, such as a header CSS rule cancelling the page padding.


```text
Commit everything (including .claude/launch.json) and push to main on ebeetles/rosetta.
```
*(Suggested-reply button.)*

### 2. Running it myself

```text
do i need to be in a virtual environment or install requirements before running python -m rosetta serve
```

```text
what does this mean:

rosetta› find growing too quickly and its detrimental instead
W1026 17:58:06.843000 68368 .venv/lib/python3.12/site-packages/torch/distributed/elastic/multiprocessing/redirects.py:35] NOTE: Redirects are currently not supported in MacOs.
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
```

```text
Add the two settings to rosetta/__main__.py, test it, then commit and push.
```
*(Suggested-reply button.)*

### 3. Web UI parity, pinyin, and English translations

```text
can we update the UI to have all the functionalities that the CLI has, and also add english translations and pinyin to all chinese idioms and chinese explanations
```

Before writing code, Claude tested a free offline translation model (`Helsinki-NLP/opus-mt-zh-en`) on real idioms. It produced "Nine cents" for 九牛一毛 and "Benson makes axes" for 班门弄斧. Claude then asked two questions (paraphrased below; my answers are exact):

- *Where should the English come from?* → picked **"Claude, cached (Recommended)"**
- *Which Claude model?* → picked **"Opus 5.5"**

- **Pinyin and English:** pinyin comes from `pypinyin` (offline). English comes from Claude in batches of 40 and is cached so it's never paid for twice. Both are stored as extra metadata, so search results didn't change.
- **Web UI:** gained a Database page (stats plus a build button with live progress), a result-count menu, and pinyin/English toggles.
- **Testing:** with no API key yet, the translation path was tested with a stand-in Claude client.

```text
Commit these changes and push to main on ebeetles/rosetta.
```
*(Suggested-reply button.)*

### 4. Debugging: "failed to fetch"

```text
did you run the translations?
```

```text
also the ui is showing failed to fetch
```

- **"Failed to fetch":** the browser pane was still showing Claude's test server, which it had stopped.
- **The Database page error:** my own server had been running since before the update. It served the new page from disk with the old Python API behind it, so the Database page crashed reading fields the old API didn't send.

The fix was restarting the server. A leftover layout bug (stat tiles wrapping) was fixed at the same time.

```text
Stop my server (PID 68494) and start it again with the new code in the browser pane.
```
*(Suggested-reply button.)*

```text
Commit the stat-tile CSS fix and push to main.
```
*(Suggested-reply button.)*

### 5. Visual design: ink-landscape background

```text
can you add some cool like parallax chinese ink calligraphy landscape visuals in the background of the UI
```

- **The scene:** mountain ranges in ink-wash style, drawn by code from a fixed seed (no image files), plus drifting mist, a faint sun, and a vertical inscription, 言外之意 ("the meaning beyond the words"), which sums up the project.
- **The parallax:** each layer moves at a different speed as you scroll.
- **Bugs fixed during testing:** birds overlapping the search controls, and a hard edge at the bottom when scrolling.

```text
Commit the landscape background and push to main.
```
*(Suggested-reply button.)*

### 6. Running the translations

```text
I have put my API key in the .env file
```

### 7. Assignment documentation

I gave Claude the assignment's deliverables only at the end, after the app was built.

```text
Seems to work well so far. Here are the rest of the requirements for my assignment. Please update the README to include sample responses to everything I need to include, and I will write them in my own words because I am supposed to write those parts in my own words.
```
*(Followed by the assignment's README, prompt-log, video, and grading requirements, pasted from the course page.)*

- **Draft answers:** Claude added draft answers for each required README item, marked for me to rewrite, and moved its own documentation under an "AI-generated documentation" heading.
- **The test queries:** for the two test queries, Claude compared the vector results against a plain keyword search over the same idioms. English descriptions often share a word with the right English idiom, so it picked two cross-language queries where a keyword search finds nothing.

```text
Draft prompt_log.md with my verbatim prompts from this session, marking what I need to fill in or rewrite.
```
*(Suggested-reply button.)*
