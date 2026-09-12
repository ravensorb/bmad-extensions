# Contributing to this project

This project welcomes contributions and suggestions. By contributing, you confirm that you have the right to, and actually do, grant us the rights to use your contribution. More information below.

Please feel free to contribute code, ideas, improvements, and patches - we've added some general guidelines and information below, and you can propose changes to this document in a pull request.

This project has adopted the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/).


## Rights to your contributions
By contributing to this project, you:
- Agree that you have either:
  - Authored 100% of the content, or;
  - the appropriate licenses and copyrights are contributed along with any other necessary attribution, following the [Developer Certificate of Origin](https://developercertificate.org/).
- Agree that you have the necessary rights to the content
- Agree that you have received the necessary permissions from your employer to make the contributions (if applicable)
- Agree that the content you contribute may be provided under the Project license(s)

## Code of Conduct
This project, and people participating in it, are governed by our [code of conduct](https://www.contributor-covenant.org/). By taking part, we expect you to try your best to uphold this code of conduct. If you have concerns about unacceptable behaviour, please contact the community leaders responsible for enforcement at
[shawn@eye-catcher.com](mailto:shawn@eye-catcher.com).

## Working in this repo

Read this before your first change — this repo has one invariant that is easy to violate by
accident, and four CI gates that will catch you.

### `skills/_shared/` holds the only editable copies

Files shared between skills are authored once in `skills/_shared/` and **generated** into each
skill's own `scripts/`, `references/` and `steps/` directories. Those per-skill copies are
build output. Editing one directly is the most common mistake here: your change will be
silently overwritten the next time anyone runs the sync, and CI will fail on the drift in the
meantime.

```bash
npm run sync:scripts                      # regenerate the per-skill copies from _shared/
node scripts/write-payload-manifest.mjs   # regenerate the per-skill SHA-256 manifests
```

Run both after changing anything under `skills/_shared/`. `sync:scripts` does **not** update
the manifests for you, and a manifest asserting a hash its file no longer has is worse than no
checksum, because it reads as a guarantee.

`skills/l3io-util-doctor/scripts/audit-backlog.py` is the exception: it is single-consumer code
that lives in its own skill and is edited in place.

### The gates

All five must pass before you open a pull request. CI runs every one of them.

| Command | What it protects |
|---|---|
| `npm run check:scripts` | Per-skill payload copies match their `_shared/` source |
| `npm run check:manifest` | Every `payload-manifest.json` hash matches the file it names |
| `npm run check:docs` | Documentation matches the code it describes — fifteen checks, including that every documented CLI subcommand exists and every `<file>.md §N` cross-reference resolves |
| `npm run check:version` | `pm-status.py`'s version marker, its `PM_STATUS_VERSION`, and `package.json` agree |
| `npm run test:scripts` | The `check-docs` self-tests |

The Python suites are run by CI directly and are worth running locally when you touch them —
see `.github/workflows/checks.yml` for the exact invocations. Note that the Python helpers run
through `uv`, which provisions their dependencies from an inline PEP 723 header, so
`test-spec-align.py` needs its documented `--with` flags; a bare `uv run --script` fails with
`ModuleNotFoundError` and is a mis-invocation rather than a failure.

### Never bump versions by hand

`pm-status.py`'s version marker, `.claude-plugin/marketplace.json` and every `module.yaml` are
written from `package.json` by the release hooks. Do not edit them, and never move a version
backwards — `self-install` refuses to overwrite a strictly newer installed copy, which would
strand every project already on the higher version.

### Documentation changes

When you change behaviour, ask three separate questions of the docs, because each finds
problems the others cannot:

1. What did this make **false**? (stale statements)
2. What did this **add** that no document describes?
3. What existing behaviour did this **change**? — the one grep cannot find, because a changed
   mode usually keeps its name. It needs reading the row that documents it.

## What should I know before I get started?
### Workflow
We use the [standard GitHub workflow](https://guides.github.com/introduction/flow/), and asking our contributors to use [semantic commits](https://nitayneeman.com/posts/understanding-semantic-commit-messages-using-git-and-angular/#common-types) to support their contributions.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) — the
release tooling derives the next version from them, so a `feat:` commit makes the next release
a minor and a `fix:` makes it a patch. Valid types are `feat`, `fix`, `docs`, `style`,
`refactor`, `perf`, `test`, `chore`, `revert` and `WIP`; suggested scopes are `l3io-pm`,
`l3io-sec`, `l3io-util`, `l3io-arch`, plus `infra` and `ci-cd`.

### Developer Certificate of Origin (DCO)
LiquidLogicLabs asks that all commits sign the [Developer Certificate of Origin](https://developercertificate.org/), to ensure that every developer is confirming that they have the right to upload the code they submit.

Sign-offs are added to the commit. Git has a  `-s` command line option to append this automatically to your commit message, and [sign offs can be added through the web interface](https://github.blog/changelog/2022-06-08-admins-can-require-sign-off-on-web-based-commits/).

### Documentation
Please document changes as you go, in `docs/`. See "Documentation changes" above for the three
questions to ask of the docs when you change behaviour.
