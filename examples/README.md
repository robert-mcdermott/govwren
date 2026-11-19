# Examples

Small programs that connect another system to GovWren. Each needs only Python's standard library, and each is meant to be read, copied, and changed.

| File | What it does |
|---|---|
| `checkpoint.py` | Asks GovWren whether a reference is approved, for a class of data. For a purchasing, ethics, or data access process that is given a reference |
| `webhook_receiver.py` | Receives GovWren's webhook messages, checks each signature, and passes them on to a chat channel or a ticket system |

[Connecting other systems](../docs/connecting.md) explains how to use them.
