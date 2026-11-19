# Adopting GovWren

This guide is for whoever is bringing GovWren into an organization: usually the person who leads AI governance, working with whoever runs the server.

It is a plan, not a manual. It says what to decide, in what order, and what to leave for later, from the first conversation to the first attestation campaign. Each step points to the guide that says how.

Plan for eight to twelve weeks from a decision to adopt to a completed first campaign. Very little of that time is spent on the software. The timings here are a plan to start from, not a record of what others took.

## Before you install anything

Four things decide how the rest goes. Settle them first, on paper.

### Who owns the program

Name one person who is answerable for AI governance, and one who stands in for them. GovWren will ask for this in the first hour, as the people who hold the **governance** role.

If nobody owns it yet, stop here. GovWren records decisions. It cannot make an organization want to make them.

### What the units are

GovWren is built for organizations where labs, departments, and centers decide a good deal for themselves. Every record belongs to a unit, and stewards answer for a unit's list.

Write down your units as a tree: the organization, its divisions or schools, the departments, and the labs or groups beneath them.

- Go as deep as people actually make decisions. If a principal investigator decides which tools a lab uses, labs are units.
- Use the names people already use. Your directory or your finance system is a better source than a new list.
- You do not need every unit on the first day. You do need the level at which you will ask someone to attest.

### Who reviews what

GovWren routes a request to review functions by rule: privacy, security, legal, ethics, research integrity, clinical safety, data stewardship, and architecture. Few organizations need all eight; four or five is usual.

For each function you will use, name one or two people. They do not need to be new roles. The privacy officer is already the privacy reviewer.

Decide also who decides. In the default program, governance decides moderate requests, a committee decides high ones, and the highest tier needs a named person to accept the risk. If you have a committee, find out when it meets: its calendar sets the pace of your slowest decisions.

### What you already know

You are not starting from nothing. Somewhere there is a spreadsheet of tools people have asked about, a list of vendors with agreements, and a memo saying which tools are allowed.

Collect them. They become your catalog and your first records, and bringing them in is how you find out what your policy actually is.

## Weeks 1 and 2: stand it up

The aim of these two weeks is an installation that the core team can sign in to, with your name on it and your structure in it. Nobody outside the core team needs to know it exists yet.

| Step | Who | How |
|---|---|---|
| Try the demo for an hour, signed in as each sample person in turn | Everyone on the core team | [Explore the demo organization](getting-started.md#explore-the-demo-organization) |
| Choose where it will run | Whoever runs the server | [Deployment](deployment.md) |
| Install, starting from the program closest to yours | Whoever runs the server | [Begin from a starter](running-the-program.md#begin-from-a-starter) |
| Connect single sign-on | Whoever runs the server | [Single sign-on](single-sign-on.md) |
| Set up email | Whoever runs the server | [Email](email.md) |
| Make it yours: name, logo, colors, your own words | An administrator | [Set the appearance](running-the-program.md#set-the-appearance) |
| Bring in units and people | An administrator | [Import units and people from CSV](running-the-program.md#import-units-and-people-from-csv) |
| Give out the roles | An administrator | [Roles and scopes](running-the-program.md#roles-and-scopes) |
| Schedule a backup, and restore one once | Whoever runs the server | [Operations](operations.md#back-up) |
| Run `govwren doctor --production` until nothing is left that you have not decided about | Whoever runs the server | [Check before people depend on it](deployment.md#check-before-people-depend-on-it) |

Three things are worth doing properly now, because they are tedious to change later:

- **Single sign-on before people.** Accounts made by single sign-on carry the organization's identity. If people start with passwords and move later, you will be merging accounts.
- **Roles from groups.** Map your directory's groups to roles and to stewardship of units, so that when someone changes job, GovWren follows without anyone remembering to tell it.
- **Your own words.** If your people say *lab* and *supplier*, set that now. The first impression of a tool that uses the wrong words is that it was made for someone else.

## Weeks 2 to 4: make the program yours

The starter program works on the first day. It is not yours until the people who will live with it have read it.

Sit the core team down with the **Program** page for two hours and go through it in this order:

1. **The data classes.** These are the most important four lines in the installation. Use your organization's own classification, with its own names and examples. People pick the right class only when they recognize their own data in it. See [The data classes](running-the-program.md#the-data-classes).
2. **The request form.** Read every question aloud. Cut any whose answer would never change a decision. Requesters forgive a form that is short.
3. **The tiers.** Take five real uses you already know about, some trivial and some serious, and run them through the preview. If the tier surprises you, change the scoring until it does not. See [How a request gets its tier](running-the-program.md#how-a-request-gets-its-tier).
4. **The routing rules.** For each tier, check who reviews, who decides, how long they have, and how long an approval lasts. The low tier should be approved by rule, the same day. That is what makes the front door a door.
5. **The standard conditions.** These are the sentences every approved use will carry. Make them ones you would be willing to enforce.

Then build the catalog. Enter the tools you have already decided about, each with its standing and the most sensitive class of data it may be used with. See [Build the catalog](running-the-program.md#build-the-catalog).

A good catalog is the single thing that most decides whether people use GovWren. If the ten tools people actually use are there, with a clear answer, most people get what they came for in a minute and register their use in another.

Bring in what you already have: [import from a spreadsheet](running-the-program.md#import-from-a-spreadsheet), with a dry run first.

Leave these for later. None of them is needed to open:

- Frameworks
- The risk register beyond what reviewers raise
- Custom fields beyond one or two you cannot do without
- Webhooks and tokens
- The transparency register

## Weeks 4 to 6: a pilot with two units

Choose two units to go first: one that is keen, and one that is typical. Not the most skeptical one. That comes later, when you have something to show.

Ask each to do three things, with you in the room the first time:

1. Look up the tools they use in the catalog, and register each use.
2. Make one real request for something that is not in the catalog.
3. Have their steward look at the unit's list and say what is missing.

Watch where they stop. Every hesitation is a question to reword, a class to explain better, or a tool to add to the catalog.

Run the requests through for real. Reviewers review, governance decides, conditions are set. This is the reviewers' practice as much as the requesters'.

At the end of the pilot, look at three numbers on the **Measures** page:

| Measure | What you want to see |
|---|---|
| Turnaround | Days, not weeks, for anything below the high tier |
| Throughput | Most requests approved by rule |
| Completeness | The pilot units' records mostly whole |

If turnaround is long, find out where the time went before you open the door wider. The review of a request shows how long it sat with each person.

## Weeks 6 to 8: open the door

Now tell everyone. The message is short:

- There is one place to ask whether you may use an AI tool, and it usually answers in a minute.
- If you already use AI in your work, register it. It takes a minute and nobody is in trouble.
- If what you want is not listed, ask. Here is how long an answer takes.

Put the address where people already look: the intranet's front page, the research office's pages, the new-starter checklist. Put your policy and your help address in GovWren's [links](running-the-program.md#set-the-appearance), so that the path runs both ways.

Connect the places where a reference should be asked for. A purchasing form, an ethics application, or a data access request that asks "what is the GovWren reference?" does more for coverage than any announcement. The receiving system can check the reference itself: see [The checkpoint](api.md#the-checkpoint).

Expect a rush in the first two weeks, mostly registrations of tools already in the catalog. That is the inventory filling up. It is the point.

Hold a short session for stewards. They need to know three things: their unit's list is theirs, **My unit** shows it on one page, and they will soon be asked to say it is complete.

## Weeks 8 to 12: the first campaign

An inventory nobody has confirmed is a list of what people remembered to tell you. The first attestation campaign turns it into something you can stand behind.

Run a **unit completeness** campaign first. Each steward looks at their unit's list, adds what is missing, and attests that it is complete. See [Attestation campaigns](keeping-watch.md#attestation-campaigns).

- Give it four weeks. Two is too short for a steward who has to ask around a lab.
- Say what happens if something is missing: nothing, except that it gets added. The first campaign is an amnesty in everything but name.
- Watch coverage by unit, and call the stewards who have not answered in the last week. A call does more than a third reminder.

When it closes, you know what you have, by unit, with a name against each list. Make your first [report to leadership](insight.md#reports-to-leadership) on that day. It is the baseline every later report is read against.

## After the first quarter

By now GovWren is doing a good deal by itself: opening periodic reviews before approvals end, reminding owners, marking approvals that nobody renewed. See [What GovWren does by itself](keeping-watch.md#what-govwren-does-by-itself).

What to add, in a sensible order:

| When | Add | Why |
|---|---|---|
| Month 4 | An owner confirmation campaign | Each owner confirms that their use is still as described |
| Month 4 | Incident reporting, announced | People need to know where to say something went wrong |
| Month 6 | The control library, with owners and evidence for the program's own controls | So that you can show the program works, not only that it exists |
| Month 6 | A quarterly report, made on the same day each quarter | Leadership learns to expect it |
| When asked | A framework | Only when an auditor, a funder, or a regulator asks how you answer one |
| When ready | The transparency register | When you are prepared to say in public how you use AI |

## What goes wrong, and what to do

| What you see | What it usually means | What to do |
|---|---|---|
| Few requests, and people still asking by email | The catalog does not hold the tools they use | Add the ten tools people actually use, with clear answers |
| Requests arrive but sit for weeks | A review function has one person, who is away, or a committee that meets monthly | Name a second reviewer. Lower the tier at which the committee is needed |
| Everything comes out high tier | The scoring counts something common as serious | Run past requests through the preview and adjust |
| Stewards do not attest | They were not told the list was theirs | Talk to them. Show them **My unit** |
| Approvals lapse in numbers | Owners ignore the reminder, or have left | Check that email is working, and that records have a second owner |
| Units keep their own spreadsheet | GovWren is missing something they need to record | Ask what. Often it is one [field of their own](running-the-program.md#add-your-own-fields) |

## What GovWren will not do

It helps to say this early, to yourself and to leadership.

- **It does not find AI use.** It has no scanners and reads no logs. It knows what people tell it, and its design is to make telling it the easy path. Coverage comes from the catalog, the checkpoints in other processes, and the campaigns.
- **It does not decide.** Rules approve what you have told them is routine. Everything else is decided by a named person, with a reason.
- **It does not replace your policy.** It holds your policy's text and records who has acknowledged it, and it applies the rules you give it. The policy is still yours to write.
