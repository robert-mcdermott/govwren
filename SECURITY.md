# Security

## Reporting a vulnerability

Please report security problems privately. On the repository's **Security** tab, choose
**Report a vulnerability**. If that is not available to you, open an issue that asks for a
private channel and gives no details.

You will get a reply within a week. Reporters are credited in the release notes unless they
ask not to be.

## Supported versions

Before version 1.0, only the latest release receives fixes.

## How GovWren is kept secure

The threat model, the controls for each threat, and the table of who may see and do what are
in [`spec/security.md`](spec/security.md). `govwren doctor` checks an installation, and
`govwren verify` confirms that the history has not been altered.

Reviews are recorded in [`spec/reviews/`](spec/reviews/). The latest covers what was looked
at, what was found and fixed, and what has not yet been done, such as a penetration test by
an outside firm.
