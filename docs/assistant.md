# Internship Assistant (FAQ chatbot)

**Prototype. Synthetic data. Not official university policy.**

An FAQ chatbot inside the IPP app for students, employers and the coordinator. It answers internship questions **only** from the approved FAQ file, shows the FAQ section as the source, and says "I don't know yet" instead of guessing.

- Page: `#assistant` (button **Ask the Internship Assistant** in the top bar of every page, on the Overview, and under *Help* in the sidebar).
- Approved FAQ: [`data/faq.txt`](../data/faq.txt), one entry per line: `Section: … | Q: … | A: …`.
- Coordinator tools: **University Administrator → Assistant FAQ** tab.

## Which approach was built

The lab recommends Approach A (Botpress) and allows Approach B (an in-browser FAQ matcher with no API key) as the fallback.

**Approach B is built and working.** Approach A needs a Botpress account and bot, which have to be created by a team member with their own login, so it could not be done from this repository. An optional, default-off Botpress mode and the setup steps are ready (see "Approach A: Botpress" below). No API key exists anywhere in the repository, and a test fails if one is ever committed.

## How it answers

There is no language model. The engine (`src/faq.js`) is plain text matching:

1. The question is lower-cased, function words are removed, and words are reduced to a stem. Groups of synonyms are merged (for example *intern / internship / work → placement*, *remotely / online / home → remote*, *overseas / international → abroad*).
2. Each FAQ entry is scored on how much of the user's wording it explains. Words weigh more when only one entry uses them. A word the FAQ has never seen (pay, visa, deadline, "on Fridays") counts double against the match.
3. An entry must overlap the FAQ **question** itself, and must either cover at least half of that question or be pinned down by a word that appears in only its answer. A single shared word (such as "apply") is never enough.
4. Below the confidence threshold (0.45), or if two entries are about equally good, the assistant answers: **"I don't know yet. I've noted your question for the coordinator."** and saves the question, as typed, to the *Unanswered questions* list.
5. A small typo repair maps a misspelt word onto a single near-identical FAQ word (for example *placments*, *oportunity*).

The reply is always the FAQ answer copied word for word. A test generates thousands of questions and checks that every reply is exactly an approved answer.

### Privacy guard

A reminder is shown beside the input. Messages that look like personal information (email addresses, phone numbers, long numbers, student IDs such as `COOP-B001`, "my name is…", passport and similar) are refused, **never echoed back, never saved**, and the chat shows "message withheld". This is a heuristic, not a guarantee. The same check rejects personal information in new FAQ entries.

## Coordinator workflow (Administrator view → Assistant FAQ)

- **Unanswered questions:** every question the assistant could not answer, with how often it was asked. *Write an answer* copies the question into the form; *Dismiss* closes it.
- **Add an FAQ entry:** Section, Question, Answer, labelled **coordinator approval required**. New entries are saved as **Pending** and the assistant does **not** use them.
- **Pending entries:** the coordinator approves or discards. Approval makes the entry available to the assistant and closes any unanswered questions it now covers.
- **Approved FAQ:** read-only list of everything the assistant can answer, with **Download faq.txt** (the updated file, ready to upload as a Botpress Knowledge Base or to commit to `data/faq.txt`).

The Administrator view is the coordinator's simulated role, so in the demo the same person adds and approves; the two steps exist to show the approval control.

## Tech stack

| Item | Choice |
| --- | --- |
| Hosting | GitHub Pages (static files only, public) |
| Chatbot platform / model | None. In-browser keyword matcher (`src/faq.js`), no language model, no third-party service |
| Where the FAQ lives | `data/faq.txt` in the GitHub repository (read-only source of truth). Coordinator additions and unanswered questions are stored in each browser's `localStorage` and can be exported as `faq.txt` |
| API keys / secrets | None. A test scans the published files for secret patterns |
| Cost and limits | $0. No usage metering. Bound only by GitHub Pages' published soft limits (about 1 GB site size and 100 GB/month bandwidth; check GitHub's current documentation) |
| Network | The page loads `data/faq.txt` and the shared seed from its own origin; questions never leave the browser |

## Known limitations

- **Unanswered questions are browser-local.** A question asked on a student's laptop is stored on that laptop, so the coordinator will not see it in their own browser. A real deployment needs a shared store (for example a database behind the chatbot platform); this is the same gap as IPP-18 (central storage).
- **Rewordings can be missed.** The matcher refuses rather than guesses, so an unusual rewording gets "I don't know yet". Known examples: a pure answer-side question such as "Will the old version be overwritten?", and a transposed typo in a short word.
- **"Will I get money?" has no FAQ entry.** None of the 8 approved entries mention pay, so the correct behaviour is "I don't know yet" (the same as "Are co-op students paid?"). The coordinator can add an approved pay entry to change that.
- The privacy guard is heuristic. Do not rely on it as a compliance control.
- The optional Botpress mode has been tested with stand-in scripts only (validation, opt-in, loading order, failure handling), not with a real Botpress bot.
- Everything here is synthetic prototype content, not official university policy.

## Approach A: Botpress

The lab recommends Botpress. The app has an **optional Botpress mode that is off** until the team creates a bot and supplies its embed URLs.

**Models and keys.** On Botpress's free plan the bot uses Botpress's built-in model, so no API key is needed. Botpress documents bringing your own LLM (for example a K2 Think key) as an [Enterprise-plan feature built with their SDK](https://botpress.com/docs/integrations/sdk/integration/use-your-own-llm/), so do not expect to paste a key into a free bot. Never put any model key in this repository: GitHub Pages is public.

**Steps for a team member with their own Botpress login** (menu names change, so treat these as a guide):

1. Create a free bot at botpress.com.
2. **Knowledge Base:** add `data/faq.txt` (or the file from *Download faq.txt*).
3. **Instructions:** set exactly: `Answer only from the knowledge base. If the answer is not there, say: 'I don't know yet. I've noted your question for the coordinator.'`
4. Test in Botpress's emulator: the 8 FAQ questions, "Can I intern remotely?", and "Are co-op students paid?" (it must say "I don't know yet").
5. Publish, open **Webchat** (embed), and copy the **two script URLs** (the inject script and the bot's config script). They are public embed URLs, not keys.
6. Put both URLs in `data/chatbot-config.json` under `botpress.scripts`, set `enabled` to `true`, then commit and push (or send them to whoever maintains the repository).

**What the app does with them.** The Assistant page then shows a card, "Prefer the Botpress assistant?". Nothing from Botpress loads until someone clicks it. Only `https` URLs on `cdn.botpress.cloud` and `files.bpcontent.cloud`, with no credentials or token-like parameters, are accepted; anything else is ignored. The built-in matcher stays available beside it.

**Cautions.** Questions typed into Botpress go to Botpress and its model provider. This page's personal-information check and the coordinator's unanswered-question list do not apply there. Never commit a Botpress API token or personal access token (the public embed URLs are fine).

## Test report (2026-11-24, Chrome 158, headless, real keystrokes into the real input)

| # | Question typed | Result | Source shown |
| --- | --- | --- | --- |
| 1 | Are placements on site? | Exact FAQ answer | FAQ · Placements |
| 2 | Can I work abroad? | Exact FAQ answer | FAQ · Placements |
| 3 | Who enters my final grade? | Exact FAQ answer | FAQ · Grading |
| 4 | What must an employer include? | Exact FAQ answer | FAQ · Employer submissions |
| 5 | How is an opportunity approved? | Exact FAQ answer | FAQ · Review |
| 6 | Why was my opportunity returned? | Exact FAQ answer | FAQ · Review |
| 7 | How do I resubmit? | Exact FAQ answer | FAQ · Review |
| 8 | Does applying mean I got the placement? | Exact FAQ answer | FAQ · Students |
| 9 | Can I intern remotely? (reworded) | "Yes. Placements are on site; remote roles are not approved." | FAQ · Placements |
| 10 | Will I get money? (reworded) | "I don't know yet. I've noted your question for the coordinator." (no FAQ covers pay) | none |
| 11 | Are co-op students paid? (unknown) | "I don't know yet. I've noted your question for the coordinator." | none, saved to Unanswered |

Further rewordings that matched correctly: "Who decides my final grade?", "What does an employer need to submit?", "Why was my listing returned?", "Is applying the same as getting the placement?", "Can I do my internship overseas?", and the typo "Are placments on site?". Questions that were correctly refused: "Can I apply?", "Is my application approved?", "Are placements on site on Fridays?".

**A failure found and fixed.** "Is my application approved?" first returned the entry *Does applying mean I got the placement?* ("No. Applying only shows interest…"), a wrong answer, because "application" overlapped the question and "approved" only appeared inside answers. The same flaw would have answered "Can I apply?" with "No." Fix: an entry must now cover at least half of its FAQ question, or be identified by a word unique to its answer, and words the FAQ has never seen count double. Both questions are now permanent regression tests.

### Rest of the browser verification (same date, same Chrome, real typing, clicking and viewports)

- **Coordinator workflow, 20 checks, all passed:** unanswered questions listed and deduplicated with a count; *Write an answer* prefills the form; the new entry is Pending and **not** used by the assistant; approving it makes the assistant answer from it (with its section as the source) and closes the unanswered question it covers; the form rejects empty fields, personal information and a duplicate of an approved question; *Download faq.txt* produces the 9 approved entries in the original format; *Reset demo data* clears everything.
- **Phone and widths, 13 checks, all passed:** no horizontal overflow at 390px on the assistant, coordinator tab, Overview, Employer and Student pages; the top-bar button becomes icon-only but keeps its accessible name; the 5-slot bottom tab bar is unchanged; typing and sending work; the top bar fits at 1000, 1100 and 1280px.
- **Also found and fixed during this run:** *Download faq.txt* was hidden inside a collapsed list (moved next to the *Approved FAQ* heading), and the top bar was cramped at 1000px (labels wrapped to three lines; they now stay on one line and the breadcrumb hides below 1280px).
- **Not tested:** a real phone or tablet, Safari or Firefox, a screen reader (the chat log is a live region with labelled controls, but this was not heard through assistive technology), and the optional Botpress mode (not built).
