# Wave 7: Connected (v0.7.0)

**Goal:** fit into the systems around it while staying passive. Others ask GovWren, or push to it. It never goes looking.

**Branch:** `wave-7` · **Target version:** `0.7.0` · **Status:** ☑ released

## Exit criteria

The wave is done when, on a fresh checkout:

1. There are worked recipes for citing and checking a GovWren reference from a purchasing process, an ethics review, and a data access request, and for sending webhook messages to a ticket system and a chat channel.
2. An optional tool server lets an AI assistant read records and draft requests and updates, which a person confirms before anything is saved.
3. Another tool can push a summary, such as an evaluation result or a monitoring report, onto a record as evidence, with a token made for that.
4. An organization can opt in to a scheduled, read-only pull of model metadata from a registry it names. What is pulled is a suggestion that a person confirms.
5. An optional assistant, off and invisible unless switched on, drafts intake answers and summarizes decision packets with any compatible provider, including a local one, and every exchange is logged.
6. The suite passes on both databases, and the accessibility audit and keyboard check pass over every new screen.

## Slices

| Slice | Name | Delivers |
|---|---|---|
| 1 | Checkpoints in practice | Recipes for citing and checking a reference from purchasing, ethics review, and data access; ticket and chat notifications by webhook |
| 2 | Tool server for assistants | An optional server through which an AI assistant reads records and drafts requests and updates that a person confirms |
| 3 | Signal intake | Other tools push a summary onto a record as evidence |
| 4 | Metadata sync | Opt-in, read-only, scheduled pulls of model metadata from a named registry; suggestions only |
| 5 | Optional assistant | Off and invisible by default; drafts and summaries with any compatible provider; every exchange logged |
| 6 | Release prep | Guides, changelog, release |

## Decisions and notes log

| Date | Note |
|---|---|
| 2026-11-19 | Wave planned at the end of wave 6. Carried forward: a person has yet to listen to GovWren with a screen reader, and no outside firm has tested a deployed installation; both are recorded in `spec/reviews/`. The compose file and the systemd unit were written but not run. API tokens survive a password change, on purpose. |
| 2026-11-19 | Slice 1. The recipes are a guide and two example programs that use only the standard library. A test runs the checkpoint example against the real service and delivers a real signed message over a socket to the example receiver, so the guide cannot drift from the product. The receiver passes on one line and a link, never content. |
| 2026-11-19 | Slice 3, taken before slice 2 because it builds on the tokens just made. A signal is a summary pushed by another tool and kept as ordinary evidence, so nothing new had to be built to show it, remind about it, or put it in a dossier. A signal token may push onto any record and read nothing; a person may push only onto what they see in full. A warning or a failure notifies the owners. GovWren still fetches nothing. |
| 2026-11-19 | Slice 2. The tool server is one module with no new dependency: JSON-RPC over standard input and output, each tool one call to GovWren's own API with the person's token. Because it goes through the API, the policy table and every service check apply unchanged, and an assistant can do nothing the API would refuse the token. Eight tools, none of which submits or decides; a draft is the most it can create. Tested against the real API with real tokens, and run once over real pipes against a demo. |
| 2026-11-19 | Slice 4. The only thing GovWren fetches, and off unless an address is in the configuration file, which only the server's operator can change. It reads a small documented shape with one GET per named model, follows no redirect, and reads at most 1 MB. What it finds is a suggestion in a table of its own; accepting one is an ordinary edit by the person, through the same service as any edit, so permissions and the history apply unchanged. A dismissed suggestion is remembered and not made again. The registry's shape is ours, not a vendor's: an organization puts a small adapter in front of whatever it runs. |
| 2026-11-19 | Slice 5. The assistant is off unless a server and a model are configured, and the web app is told only then, so nothing mentions it otherwise. It does two things: suggests form answers, which pass through the same checks as typed answers and are never saved or submitted for the person; and summarizes a review for those who see reviewers' notes, shown beside the packet and not kept on the record. A request above `max_data_class`, which starts at Internal, is never sent. Every exchange is a row with what was sent and what came back, failures included, and an event in the history. The provider is whatever offers the chat completions interface. Proven end to end with a stand-in model server by `scripts/capture-assistant.mjs`; no real model was used, so the quality of its suggestions is untested. |
| 2026-11-19 | Slice 6. Released as 0.7.0. The stability wave was planned next, and is now [wave 9](wave-9.md). |
