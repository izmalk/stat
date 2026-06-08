# Automated Tutorial Testing: Let's Make Our Tutorials Trustworthy

## Short summary

We have working solutions for automatically testing tutorials by extracting shell commands from documentation pages and running them in clean VMs. No AI, no flakiness: deterministic scripts that either pass or fail. If your product has a tutorial, you can plug into this today. If you have your own approach, let's share notes.

## Rationale

Tutorials often involve lengthy multi-step procedures: provisioning infrastructure, deploying services, waiting for components to stabilise, configuring integrations. In my case (Charmed Apache Kafka and Spark), a single tutorial run takes 30-60 minutes and involves Juju, LXD, multiple charm units, and inter-application relations. But the same problem applies to any product with a non-trivial tutorial.

Testing a tutorial is the only sure way to verify that it stays correct as the product, its dependencies, and the platform evolve. Doing that manually takes effort, doesn't scale, and boring. So we automate.

## Can we use AI for that?

Of course we can, just not directly for testing. While it is possible to ask agentic AI to test your tutorial, it is very inefficient to do so. It takes a lot of time and tokens, and the results are unpredictable. Firing up a model with the whole tutorial in its context in agentic mode and asking it to run a VM to test every single command and check outputs can provide interesting insights when done once, but easily becomes too expensive to run regularly across many products.

Additionally, AI can be confused by some simple issue that wouldn't be an issue for a user. The opposite is also true: AI can miss a problem because it already has some idea of the underlying technologies from its training that users might lack.

The better approach is not to use AI to reason about your tutorial each time, but rather to use AI to help you create a deterministic testing harness once. One that relies as much as possible on the tutorial itself, because the commands are already there. And if the tutorial gets updated, tests are simply regenerated from its content with all the updates.

Benefits of the deterministic approach:

- **Cost**: a full tutorial run takes 30-60 minutes of compute. No LLM API calls per step, no token costs.
- **Reproducibility**: the generated script is a plain bash file you can read, re-run, and debug line by line. No "the model interpreted the instruction differently this time."
- **Reliability**: a script that extracts the exact commands from the page produces the same result every time, given the same environment. No flakiness.
- **Speed of diagnosis**: when a step fails, you SSH into the VM and see the exact state. No guessing what the AI decided to do.

## Existing solutions

### STAT (Spread Tutorial Automated Testing)

Extracts shell blocks from MyST Markdown pages, respects HTML-comment annotations for wait points/assertions/retries, generates Spread tasks, runs them in a Multipass VM.

- **Repository**: https://github.com/izmalk/stat
- **Design article**: https://github.com/canonical/data-kb/pull/47
- **Used by**: [Charmed Apache Kafka](https://github.com/canonical/kafka-operator/tree/main/tests/tutorial), [Charmed Apache Spark](https://github.com/canonical/spark-k8s-bundle/tree/main/python/tests/tutorial)

Key characteristics:
- Single source of truth: annotations live in the tutorial `.md` file itself (invisible to readers)
- Supports waiting for Juju idle, retries, hidden assertions, variable capture, timeouts
- Debug mode: SSH into the VM at the point of failure

### operator-workflows spread task generator

Generates Spread task files from tutorial documentation, integrated into the operator-workflows CI system.

- **Script**: https://github.com/canonical/operator-workflows/blob/main/spread/create_spread_task_file.py
- **Documentation**: https://documentation.ubuntu.com/platform-engineering/latest/engineering-practices/documentation/automated-quality-testing/

## Join in

**Try it out**: both solutions use Spread (see the [quick start guide](https://documentation.ubuntu.com/sphinx-stack/latest/how-to/optional-customisation/add-documentation-testing/)). Pick one, see if it fits your tutorial, and let us know how it goes.

**Share your work**: if you already have something similar, post it here. We want to know what exists across teams.

**Give feedback**: reply below, reach out directly, or open a GitHub issue on the relevant repo. Some questions we'd love input on:

- What blocks you from testing your tutorials today?
- Are there edge cases the current annotations don't handle?
- Should we converge on a single approach across Canonical?
- Are there tutorials that _can't_ be tested this way? What makes them different?

The goal is to get every product tutorial under automated testing, so we stop finding out they're broken from user bug reports.
