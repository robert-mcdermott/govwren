# Connecting other systems

This guide is for whoever connects GovWren to the systems around it: purchasing, ethics review, data access, tickets, and chat.

GovWren stays passive. It does not reach into other systems, scan them, or read their logs. Other systems ask it a question, or it tells them that something happened. The two tools for that are the [checkpoint](api.md#the-checkpoint) and [webhooks](api.md#webhooks), and this guide shows how to use them for five common jobs.

The programs it mentions are in the [`examples/`](https://github.com/robert-mcdermott/govwren/tree/main/examples) directory of the repository. Each needs only Python's standard library, and each is short enough to read before you run it.

## The idea: cite a reference, then check it

Every use of AI that GovWren knows about has a reference, such as `UC-0042`. Every tool in the catalog has one too, such as `SYS-0007`.

The pattern is the same wherever you apply it:

1. A form in another process asks for the GovWren reference.
2. The system behind the form asks the checkpoint whether that reference is approved, and for what data.
3. It goes ahead only on a yes.

This does more for coverage than any announcement. People record their use of AI because the next thing they want to do asks for the reference.

### Make a token for the other system

Each system that asks the checkpoint needs a token.

1. Make an account for the system, such as `purchasing-system@example.org`, with no roles beyond the ordinary.
2. Sign in as that account, open **Your account**, then **Manage your tokens**, and make a token with the scope **checkpoint**.
3. Give the token to whoever runs the other system. It is shown once.

A checkpoint token can ask whether references are approved and can do nothing else. It learns a record's standing, never its content, and is given a record's name only if its account could see the record anyway.

### Ask from a script

`examples/checkpoint.py` asks the question and reads the answer:

```bash
export GOVWREN_URL=https://ai.example.org
export GOVWREN_TOKEN=gw_...
python3 examples/checkpoint.py UC-0042 protected
```

```text
Yes. UC-0042 is approved for protected data until 2027-05-01.
```

| It exits with | Meaning | What your system should do |
|---|---|---|
| 0 | Approved, and it covers that class of data | Go ahead |
| 1 | Not approved, not for data that sensitive, or no such reference | Stop, and show the person the sentence it printed |
| 2 | GovWren could not be asked | Hold the request and try again. Never treat this as a yes |

To call it from your own code instead, copy its two functions, `ask` and `decide`.

## Recipe: purchasing

**The job:** nobody buys or renews an AI tool that governance has not approved.

1. Add a field to the purchase request: *GovWren reference for this tool*. Say where to find it: the tool's page in the catalog.
2. When a request names an AI tool, check the tool's reference, which begins `SYS-`:

   ```bash
   python3 examples/checkpoint.py SYS-0007
   ```

3. On a no, send the requester to GovWren to [ask for the tool to be evaluated](requesting.md). On a yes, record the reference on the purchase order.

For a renewal, check again. A tool approved last year may have been withdrawn.

To hear about changes without asking, add a webhook for **An AI system's or a model's standing in the catalog changes**, and have purchasing's system flag open orders for a tool that is no longer approved.

## Recipe: ethics review

**The job:** a protocol that uses AI on human-subjects data names the use, and the use is approved for that data.

1. Add a question to the application: *Does this study use AI on participants' data? If so, give the GovWren reference.*
2. Check the use case, which begins `UC-`, for the class of data the protocol involves:

   ```bash
   python3 examples/checkpoint.py UC-0042 restricted
   ```

3. A no because the approval covers less sensitive data is the useful case. The researcher [declares a change](keeping-watch.md#declare-a-change) in GovWren, and the use is reviewed again for the new data.

Going the other way, a reviewer in GovWren can record the protocol number on the use case under [Point to other systems](running-the-program.md#point-to-other-systems), so that each record names the other.

## Recipe: data access

**The job:** a dataset is released for use with an AI tool only if that tool may hold data of its class.

1. The data access request asks which AI tool, if any, the data will be given to, by reference.
2. Check the tool for the dataset's class:

   ```bash
   python3 examples/checkpoint.py SYS-0007 protected
   ```

3. On a no, the answer says what the tool is approved for, which is usually enough for the requester to choose another tool.

If the use of the data is itself a use of AI, ask for the use case's reference as well and check it the same way.

## Recipe: a ticket when an incident is reported

**The job:** the service desk hears of an AI incident at once, in the system it already works in.

1. Run `examples/webhook_receiver.py` somewhere the service desk's system can be reached from, behind a reverse proxy with TLS:

   ```bash
   export GOVWREN_WEBHOOK_SECRET=whsec_...
   export FORWARD_URL=https://desk.example.org/api/incoming/abc
   export GOVWREN_URL=https://ai.example.org
   python3 examples/webhook_receiver.py 8099
   ```

2. In GovWren, under **Admin → Webhooks**, add a webhook to the receiver's address for **An incident is reported**. Copy the signing secret it shows into `GOVWREN_WEBHOOK_SECRET`.
3. Choose **Send a test**. The receiver passes on `A test message from GovWren arrived.`

The receiver checks each message's signature, refuses one more than five minutes old, and passes on a message that arrives twice only once. What it passes on is one line with a link:

```text
An incident was reported: INC-0003. https://ai.example.org/incidents/INC-0003
```

The message says that an incident was reported and where to read it. It does not say what happened: that stays in GovWren, for the people allowed to see it. To make a ticket rather than a line of text, change the receiver's `forward` function to send what your ticket system expects.

## Recipe: decisions in a chat channel

**The job:** the governance team's channel shows each decision as it is made.

Most chat systems give a channel an *incoming webhook* address that accepts JSON with a `text` field. The example receiver sends exactly that.

1. Create an incoming webhook for the channel in your chat system, and set `FORWARD_URL` to its address.
2. In GovWren, add a webhook for **A review is decided**, and for **A use case's standing changes** if you want lapses and suspensions too.

```text
UC-0042 was decided: approved with conditions, until 2027-05-01. https://ai.example.org/use-cases/UC-0042
```

Post decisions to a channel only governance reads. A reference and an outcome are not secret, but a public feed of who was declined is not kind.

## Recipe: results from an evaluation or a monitor

**The job:** when a model's nightly evaluation fails, or a monitor sees drift, it shows on the model's record and its owners hear about it.

GovWren does not fetch results. The tool that has them pushes a short summary, called a signal, and GovWren keeps it as evidence on the record.

1. Make an account for the tool, and a token for it with the scope **signal**. That token can push signals and do nothing else. It cannot read anything.
2. Have the tool call GovWren when it has something to say:

   ```bash
   export GOVWREN_URL=https://ai.example.org
   export GOVWREN_TOKEN=gw_...
   python3 examples/push_signal.py MDL-0007 fail "Nightly accuracy check" \
     --source "Eval harness" --kind evaluation \
     --summary "Accuracy fell from 0.94 to 0.81 on the held-out set." \
     --url https://eval.example.org/runs/881
   ```

   ```text
   Kept as EV-0231 on MDL-0007.
   ```

| You send | Means |
|---|---|
| `ref` | The record the result is about: a model, a system, a use case, or a dataset |
| `result` | `pass`, `warn`, `fail`, or `info` |
| `title` and `source` | What was checked, and which tool is saying so |
| `kind` | `evaluation`, `monitoring`, `scan`, or `other` |
| `summary` | A few sentences. Never the data itself |
| `url` | Where the full result can be read, in the tool that produced it |
| `good_until` | The day this result stops being current. GovWren reminds the owner before then |

What happens next:

- The signal appears with the record's evidence, dated, with the tool's name and the result.
- On `warn` or `fail`, the record's owners get a notice with a link to the record.
- A failed result does not change the record's standing by itself. It is a prompt for a person: the owner decides whether to [report an incident](keeping-watch.md#report-an-incident) or [declare a change](keeping-watch.md#declare-a-change).
- If a control asks for this kind of evidence, attach the signal's evidence to the control when you check it.

Send only what matters. A pass every night is noise; a pass each week with a `good_until` a week later keeps the evidence current without filling the record.

## An AI assistant that can read GovWren

**The job:** a researcher asks their AI assistant "may I use this tool with patient data?" and gets GovWren's answer, or asks it to start a request and finds a draft waiting.

GovWren includes an optional tool server for assistants. It speaks the Model Context Protocol, which many assistant programs use to reach tools. It is not needed to run GovWren, and nothing runs unless you start it.

### What an assistant can and cannot do

| It can | It cannot |
|---|---|
| Search records, and read one | Submit a request |
| Look a tool up in the catalog | Approve, decline, or decide anything |
| Ask the checkpoint whether a reference is approved | Change a record |
| See what is waiting on the person | See anything the person cannot |
| Read the request form's questions | |
| Begin a request as a draft, and fill in answers | |

A draft is only a draft. It sits in GovWren until the person opens it, reads every answer, and submits it themselves. The assistant is told to say so and to give the link.

The assistant works as the person. It uses an API token the person made, so it sees exactly what that person sees.

### Set it up

1. In GovWren, open **Your account**, then **Manage your tokens**, and make a token. Choose **read** if the assistant should only look things up, or **write** if it may also draft requests. Give it an end date.
2. Tell your assistant program to start GovWren's tool server. Most take a configuration like this:

   ```json
   {
     "mcpServers": {
       "govwren": {
         "command": "uv",
         "args": ["run", "--directory", "/path/to/govwren", "govwren", "tools", "serve"],
         "env": {
           "GOVWREN_URL": "https://ai.example.org",
           "GOVWREN_TOKEN": "gw_..."
         }
       }
     }
   }
   ```

3. Ask the assistant something GovWren knows: *Is SYS-0007 approved for protected data?*

The tool server needs GovWren's code on the person's machine, but no installation of it: it only calls your GovWren over the network.

### What to think about first

- **What the assistant reads goes to its provider.** A record's content is sent to whichever AI service the assistant uses, like anything else the person shows it. Before you tell people about this, check that the assistant is one your organization has approved for the class of data in your records. GovWren's own catalog is the place to record that.
- **A token is a key.** It sits in the assistant's configuration file. Use an end date, and revoke it when the person stops using the assistant.
- **Start with read.** A read token cannot create anything.

## Keep it working

- **Watch the deliveries.** **Admin → Webhooks** shows each webhook's recent deliveries, and **Admin → Operations** shows how many are waiting or given up on.
- **A webhook that fails twenty times in a row is paused.** Fix the receiver, then choose **Switch on**.
- **Rotate a token** by making a new one, giving it to the other system, and revoking the old one.
- **When a system is retired,** revoke its token and remove its webhook. Disabling its account stops its tokens too.
