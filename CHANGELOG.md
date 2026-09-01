# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

## [2.4.13](https://github.com/ravensorb/bmad-extensions/compare/2.4.12...2.4.13) (2026-09-01)


### Features

* **l3io-pm:** add --runtime codex enforcement with 3-class token capture ([b8de482](https://github.com/ravensorb/bmad-extensions/commit/b8de48233a876585920d2045ab7d4f3efe8a24dc))
* **l3io-pm:** add --runtime copilot enforcement with scalar token capture ([688188a](https://github.com/ravensorb/bmad-extensions/commit/688188abda5292c51495d5cab67816d382ac730e))
* **l3io-pm:** add list-plan mode to l3io-pm-help ([8568af6](https://github.com/ravensorb/bmad-extensions/commit/8568af65fcd5fbb0e0772661b519bf2bcfff6beb))
* **l3io-pm:** extend runtime choices to codex and copilot, add OpenAI token rates ([6b30d50](https://github.com/ravensorb/bmad-extensions/commit/6b30d50faffb4f916b1347c4f61c39102ce6a806))
* **l3io-pm:** extend runtime detection to codex and copilot in step-00-activate ([e5d0f5f](https://github.com/ravensorb/bmad-extensions/commit/e5d0f5f7700d17cb1f896e48513d3819db4af598))
* **l3io-pm:** multi-runtime estimation support (codex, copilot) ([4efcf4e](https://github.com/ravensorb/bmad-extensions/commit/4efcf4e1ade44a36ed9d8f71b1102680a225a992))
* **l3io-util:** add bootstrap-state mode for bmad-create-story projects ([ecfc73d](https://github.com/ravensorb/bmad-extensions/commit/ecfc73d735ec959c79138653a984f8ffbb0c815e))
* **l3io-util:** align multi-runtime support with BMad AGENTS.md convention ([42631e0](https://github.com/ravensorb/bmad-extensions/commit/42631e03494e08d51cd6620e445dfb777a765bf2))
* **l3io-util:** detect and surface planning-vs-execution model mismatch ([d835554](https://github.com/ravensorb/bmad-extensions/commit/d835554da42f79287ffd6de6c45f1d44971b91ac))
* **l3io-util:** update OpenAI token rate table for GPT-5.6 family ([e11256d](https://github.com/ravensorb/bmad-extensions/commit/e11256d3ebe335d433b08085484e922069276fdc))


### Fixes

* **l3io-pm:** add verify runtime choice tests and TOKEN_RATES assertions ([d5f1bf6](https://github.com/ravensorb/bmad-extensions/commit/d5f1bf6bd89761bcad937d960b49b484867f6d29))
* **l3io-pm:** create story artifact file if absent before elaboration ([9ff7d0b](https://github.com/ravensorb/bmad-extensions/commit/9ff7d0bce8cbb37c2db53e50bb1943a6bb5503ae))
* **l3io-pm:** detect artifact-only stories before readiness check ([e2223e6](https://github.com/ravensorb/bmad-extensions/commit/e2223e6a5d672b99667dbd1367472aa393daf998))
* **l3io-pm:** fix codex tokens-na error message, update CLI docstring ([c1daa77](https://github.com/ravensorb/bmad-extensions/commit/c1daa772a6af34796b1ea7da01e6f1af540dffcd))


### Documentation

* add estimation-guide for multi-runtime token capture ([ebad2fa](https://github.com/ravensorb/bmad-extensions/commit/ebad2faa5219d1e2000ecb2883179f45153a6dfb))
* **l3io-pm:** add implementation plan for bootstrap and story-creation fixes ([46a4031](https://github.com/ravensorb/bmad-extensions/commit/46a40316ecd4a88b192ba40f053ae8581be366d7))
* **l3io-pm:** update metrics-contract §3 with four-runtime capture procedures ([6114efb](https://github.com/ravensorb/bmad-extensions/commit/6114efb93a845b4cd17b46e0d6b6361222a12f20))
* **l3io-util:** document cross-runtime planning and model mismatch behavior ([6d96c09](https://github.com/ravensorb/bmad-extensions/commit/6d96c091af914d0c139fb355ea4967a96909deae))
* **readme:** clarify post-install step and tighten upgrading section ([ab342c9](https://github.com/ravensorb/bmad-extensions/commit/ab342c94cc13c6a8c1f2df851253b9762221d541))


### Maintenance

* regenerate payload manifests after metrics-contract docs update ([afd725b](https://github.com/ravensorb/bmad-extensions/commit/afd725bc2783d828bd80b3e216fb48e1d102b49c))
* **release:** sync manifests and payload copies after multi-runtime estimation ([65bd905](https://github.com/ravensorb/bmad-extensions/commit/65bd90595eca27197f3d050a0d4ff6b513b97545))

## [2.4.12](https://github.com/ravensorb/bmad-extensions/compare/2.4.11...2.4.12) (2026-08-31)


### Features

* **l3io-pm:** add max_turns_per_story soft cap to customize.toml ([e7f5780](https://github.com/ravensorb/bmad-extensions/commit/e7f578027414ccebe028ad8155a6371aeb101adb))
* **l3io-pm:** add per-story turn cap to agent_contract ([c71b393](https://github.com/ravensorb/bmad-extensions/commit/c71b393695fd1cb60d947e75e68776807682d83b))
* **l3io-pm:** bind six per-role model keys at activation ([9543eb8](https://github.com/ravensorb/bmad-extensions/commit/9543eb8ae87e22d67fbf4d30208dc1fef97e3456))
* **l3io-pm:** model_review routing and two-tier test strategy in dev loop ([32f3518](https://github.com/ravensorb/bmad-extensions/commit/32f3518b99b1219f279241d0ede42f03c481696d))
* **l3io-pm:** per-role model routing in epic loop dispatch (prep/story/closure) ([fdf0993](https://github.com/ravensorb/bmad-extensions/commit/fdf099371f0fa37c3b1f385278549858b6cd1378))


### Fixes

* **ci:** guard max_turns_per_story doc quote in check:docs config-values check ([257bd5c](https://github.com/ravensorb/bmad-extensions/commit/257bd5cd82e4fe7c545a79167c69727326880726))


### Documentation

* add cost-optimization model routing and turn-reduction design spec ([ff9be88](https://github.com/ravensorb/bmad-extensions/commit/ff9be8809adc1d9396e130f4bc320d12ac709424))
* add implementation plan for cost optimization model routing ([60d1793](https://github.com/ravensorb/bmad-extensions/commit/60d179325b993404f9a82b21f5dab31ff8ad1bb4))
* **l3io-pm:** document per-role model routing config keys and turn cap binding ([b57d49d](https://github.com/ravensorb/bmad-extensions/commit/b57d49d8469ed037668a4bf669a87dabe5fdd4e3))


### Maintenance

* **l3io-pm:** sync shared steps and regenerate manifests after model routing changes ([4d0884e](https://github.com/ravensorb/bmad-extensions/commit/4d0884eb11c817355ee19c772ad23736be75727c))

## [2.4.11](https://github.com/ravensorb/bmad-extensions/compare/2.4.10...2.4.11) (2026-08-29)


### Features

* **l3io-util:** wire calibration redrive into the doctor's health check ([fc8b4cc](https://github.com/ravensorb/bmad-extensions/commit/fc8b4cc42247409c8891c3ebbdfb5cc8ed96de31))

## [2.4.10](https://github.com/ravensorb/bmad-extensions/compare/2.4.9...2.4.10) (2026-08-27)


### Features

* **l3io-pm:** add epic-level security review to epic closure ([996f2e0](https://github.com/ravensorb/bmad-extensions/commit/996f2e08de8f099505e59e9fdd430785674b9489))


### Fixes

* **l3io-pm:** scope redteam to a seed set, not a diff fence, at sprint closure ([8b09534](https://github.com/ravensorb/bmad-extensions/commit/8b095342ba3ac26a6dcdcca02409e26212e19868))


### Documentation

* correct arch-drift severity vocabulary in two docs ([ab61006](https://github.com/ravensorb/bmad-extensions/commit/ab610068136e28ec3aea58089aa166a271ca440d))

## [2.4.9](https://github.com/ravensorb/bmad-extensions/compare/2.4.8...2.4.9) (2026-08-26)


### Fixes

* **l3io-arch:** correct closure gate mode and severity vocabulary ([6717d4c](https://github.com/ravensorb/bmad-extensions/commit/6717d4c7bf07503acbdfa60b52c22abb1ae9fdb9))
* **l3io-pm:** enforce mutual exclusion in the epic ownership lock ([6c35334](https://github.com/ravensorb/bmad-extensions/commit/6c353346e0ac2b0da6a20034939a0bc24b477cd4))
* **l3io-sec:** correct sanctum path assertion in orphaned test ([e8c4c8a](https://github.com/ravensorb/bmad-extensions/commit/e8c4c8a44c477537aac2a36d460f422e4b82cc47))
* **l3io-sec:** make sanctum creation test call the real entry point ([56f150d](https://github.com/ravensorb/bmad-extensions/commit/56f150d5d988b7fc7919611bab581f271b4dca49))
* **l3io-util:** make util-doctor own pm-status.py self-install, detect staleness in pm-help ([0f8a165](https://github.com/ravensorb/bmad-extensions/commit/0f8a165b1efa1093499ce9e3be5bfb710d789282))
* **l3io-util:** stop the legacy migration inventing tests_passing ([c7bc0a4](https://github.com/ravensorb/bmad-extensions/commit/c7bc0a4b210b97656777e4c04cc8db4f0161b3c0))


### Documentation

* correct seven verified defects in first-read docs ([747dba4](https://github.com/ravensorb/bmad-extensions/commit/747dba4feecfa3ba67c242be7a331a2c83cacbb2))
* correct twelve verified defects across four reference docs ([aa099ed](https://github.com/ravensorb/bmad-extensions/commit/aa099ed00eb23e06aecbf7d088559c0ba5794ac4))
* fix thirteen verified defects in CLAUDE.md and status-files.md ([ea872c3](https://github.com/ravensorb/bmad-extensions/commit/ea872c35f3b33882bc70145cb7a46b64d08c8d8d))
* **l3io-pm:** document 6 missing pm-status.py subcommands, guard the gap ([52f80b4](https://github.com/ravensorb/bmad-extensions/commit/52f80b46df4910ab5948fc4e2f816bee9cd2e030))
* **l3io-sec,l3io-util:** move stray decision logs out of shipped payload, correct stale claims ([e8bcec9](https://github.com/ravensorb/bmad-extensions/commit/e8bcec9e3411b2c241ef836e5af4851c334dafad))


### Maintenance

* **l3io-pm,l3io-sec,l3io-util,l3io-arch:** stop shipping test suites into skill payloads ([91ef0cf](https://github.com/ravensorb/bmad-extensions/commit/91ef0cf842e10897a70a8114d6df0e400caa2792))


### CI/CD

* **l3io-sec:** wire test-init-sanctum.py into checks workflow ([2f19a0c](https://github.com/ravensorb/bmad-extensions/commit/2f19a0c528d95db393e8eb0d352c46fab039170c))

## [2.4.8](https://github.com/ravensorb/bmad-extensions/compare/2.4.7...2.4.8) (2026-08-26)


### ⚠ Incompatible CLI change

* **l3io-pm:** `pm-status.py set-field --field completion_evidence.tests_passing` now **exits 2**
  where it previously exited 0 and wrote the value. The field is derived, not asserted: record
  what you actually ran with `add-test-run --story KEY --command CMD --exit-code N`, and
  `tests_passing` is computed as `all(exit_code == 0)` over the **last run of each distinct
  command** in `completion_evidence.test_runs`. Every recorded run is kept, so a command that
  failed and was re-run green closes `true` with both runs still visible in the record.

  **Who this breaks:** any bespoke closeout script or hand-rolled automation that set
  `tests_passing` directly. Replace that one call with one `add-test-run` per test command;
  there is no flag to restore the old behavior, because a boolean an agent writes about its own
  work is not falsifiable — a story once shipped `tests_passing: true` having broken a suite it
  never ran, and the break surfaced two stories later.

  Reading is unaffected: `tests_passing` still appears in the same place with the same meaning,
  and a story that recorded no runs leaves it **absent** rather than `true`.

### Features

* **infra:** gate the per-skill payload manifests ([c0df507](https://github.com/ravensorb/bmad-extensions/commit/c0df507e37b83995f6e1da00637f6523f975e556))
* **infra:** ship a checksum manifest for payload copies ([e416011](https://github.com/ravensorb/bmad-extensions/commit/e416011cafa44360ce4394df8589dad4c5b7a086))
* **l3io-pm:** carry read cost to the agents that pay it ([79a0bd1](https://github.com/ravensorb/bmad-extensions/commit/79a0bd1bd21734f1c6a11e8e4990b9535b5476ac))
* **l3io-pm:** make tests_passing derived evidence, not an assertion ([ea8518b](https://github.com/ravensorb/bmad-extensions/commit/ea8518b7f6990123c3f24c55399b57560f5940f1))
* **l3io-pm:** write status back to the story document ([110fbb2](https://github.com/ravensorb/bmad-extensions/commit/110fbb2e4d1db1333aee87a0bea4718b9b7a69da))


### Fixes

* **infra:** move payload manifest to per-skill, reachable locations ([057bf18](https://github.com/ravensorb/bmad-extensions/commit/057bf181ad8e6eccf1a6b4680144f617c951b18b))
* **l3io-arch:** assign ADR numbers from a register before dispatch ([a271e75](https://github.com/ravensorb/bmad-extensions/commit/a271e75a283e1d6940640d22dfe5a2155bdfd585))
* **l3io-arch:** never block the gate on a prompt; scope the re-validation ([a3bf6ae](https://github.com/ravensorb/bmad-extensions/commit/a3bf6aed97b09d7e8a12e3893286cbf3a7c0569c))
* **l3io-pm:** bind {n} and {N} explicitly in step-05-epic-loop.md §6 ([4256059](https://github.com/ravensorb/bmad-extensions/commit/42560592b06c1d10d9959b3ff67c36781f77ce8b))
* **l3io-pm:** bind post-sprint re-estimation into the sprint loop ([a55d97d](https://github.com/ravensorb/bmad-extensions/commit/a55d97d1f34e7bfde5064a2c09089448def78ab2))
* **l3io-pm:** block on degraded plan state instead of pausing for input ([7896e0d](https://github.com/ravensorb/bmad-extensions/commit/7896e0df8dec9ba1a9bc1262d1e1a205d2e4707e))
* **l3io-pm:** close remaining hand-rolled BL-key sites and a malformed-backlog crash ([1abc18b](https://github.com/ravensorb/bmad-extensions/commit/1abc18bc4b8727141fdc4ac3723d559ed1a3bf2f))
* **l3io-pm:** close two contract gaps that stranded live runs ([5cb74cc](https://github.com/ravensorb/bmad-extensions/commit/5cb74ccefc6b261bc82e4bb48951ae3c9d5bae56))
* **l3io-pm:** deduplicate read-cost figures and name the Files-in-scope source ([b68da3c](https://github.com/ravensorb/bmad-extensions/commit/b68da3c140b820fe238c33a59572d4f75b5a3875))
* **l3io-pm:** derive tests_passing from the last run of each command ([46681c8](https://github.com/ravensorb/bmad-extensions/commit/46681c84c7bb0cce26b77dd2bf3bec8fa79418c4))
* **l3io-pm:** drop vestigial multi-story language and wire the review transition ([8663b7b](https://github.com/ravensorb/bmad-extensions/commit/8663b7b2aae07dc58aef12da152130452b515f8a))
* **l3io-pm:** give agents a procedure for required test coverage, and harden add-test-run ([c90e0d7](https://github.com/ravensorb/bmad-extensions/commit/c90e0d7bc0308ee63909276d0832d8423455c581))
* **l3io-pm:** ignore zero closure samples on read, not only on write ([53e774e](https://github.com/ravensorb/bmad-extensions/commit/53e774e92038a4ada7108e77361144595cdc47a2))
* **l3io-pm:** make append-issue duplicate-safe and self-allocating ([625a0c5](https://github.com/ravensorb/bmad-extensions/commit/625a0c57c0f12cc306178012c62bfc505a2d04c3))
* **l3io-pm:** make post-sprint re-estimation do something ([7fe74fe](https://github.com/ravensorb/bmad-extensions/commit/7fe74fe740373921084d792a565631955989734c))
* **l3io-pm:** move the fix-loop-cap FAILED literal after its state actions ([03f30f6](https://github.com/ravensorb/bmad-extensions/commit/03f30f6fa306fc1a3d9415cf4548ea8568982bcc))
* **l3io-pm:** never let a malformed frontmatter crash sync-story-doc ([7c90ccf](https://github.com/ravensorb/bmad-extensions/commit/7c90ccfc74b2f2eb58393a7c5d45498757ce151e))
* **l3io-pm:** produce Files in scope on every path, and repair the story contract ([b5fc216](https://github.com/ravensorb/bmad-extensions/commit/b5fc2161fb5ba92f7a0bf265526048ea7e477d0d))
* **l3io-pm:** reuse _is_number in active_closure_ratio instead of a bare isinstance check ([bd142a8](https://github.com/ravensorb/bmad-extensions/commit/bd142a81a41293417fdbffad4b5b2e684655c3b0))
* **l3io-pm:** source re-estimation keys and report from real CLI output ([af0c717](https://github.com/ravensorb/bmad-extensions/commit/af0c717141a714aaee4ccfa9ec2ecb1f5e92c2a4))
* **l3io-pm:** state the C x T cost model and bound the dev agent's reads ([5a5419a](https://github.com/ravensorb/bmad-extensions/commit/5a5419a683d0b96678620d7f5cc30654787db5d2))
* **l3io-pm:** state what actually unblocks a red plan ([3ca3dbc](https://github.com/ravensorb/bmad-extensions/commit/3ca3dbc71ba1f4991c2468c970de2be8aa016cfb))
* **l3io-pm:** sync CLI reference derivation text and route 5c through 5d on FAILED ([23c6ca8](https://github.com/ravensorb/bmad-extensions/commit/23c6ca840b96724abd42088682650cd2666a3a5c))
* **l3io-util:** point runtime directives at runtime paths ([1298542](https://github.com/ravensorb/bmad-extensions/commit/1298542eed61f7cefc5a81f5c5a7b6b67ef63b61))


### Performance

* **l3io-pm:** code review returns a pointer, not its findings ([7765f70](https://github.com/ravensorb/bmad-extensions/commit/7765f70dc7115d0d1683792115a2bb76041ff9de))


### Documentation

* **l3io-pm:** wire append-issue's auto-allocated key into steps and reference docs ([4e9bd1b](https://github.com/ravensorb/bmad-extensions/commit/4e9bd1bb87d170157277596e134dc1f3c1081aee))
* record the new pm-status.py surface and one incompatible narrowing ([2aa1838](https://github.com/ravensorb/bmad-extensions/commit/2aa18387c7b7bb67514a38166fa3eb0f7a7c2b30))
* record the production findings report and its cleanup plan ([c5b09fb](https://github.com/ravensorb/bmad-extensions/commit/c5b09fb3b80711d3b056d93f4fe7ed2885ebc672))
* size the digest budget raise once for both tasks that need it ([8c6e10e](https://github.com/ravensorb/bmad-extensions/commit/8c6e10ee63818c9ef16425f6f27f4d51d2308589))


### Maintenance

* **infra:** ignore .superpowers/ subagent-driven-development scratch ([b3685ac](https://github.com/ravensorb/bmad-extensions/commit/b3685acd81f4357d3919ccdbc19f6e16648c1dbe))
* **l3io-pm:** regenerate payload manifests for the append-issue changes ([22040c6](https://github.com/ravensorb/bmad-extensions/commit/22040c6f69abf57cf037d082f2b8dac6ce198f8a))


### Testing

* **l3io-arch:** prove adr-reserve's lock under real concurrency, refuse a corrupt reserved list ([c6fac32](https://github.com/ravensorb/bmad-extensions/commit/c6fac32a868d89258d50a858f54fedeb1a475ecd))

## [2.4.7](https://github.com/ravensorb/bmad-extensions/compare/2.4.6...2.4.7) (2026-08-20)


### Fixes

* **l3io-pm:** scope the usage reader to a node, and find subagent transcripts ([a8edd85](https://github.com/ravensorb/bmad-extensions/commit/a8edd8560f5cd9a35882c73bcbe71f6c0edd77d9))
* **l3io-pm:** type fix_iterations, and add calibration redrive to repair samples ([b497bf3](https://github.com/ravensorb/bmad-extensions/commit/b497bf31d24a5ec84dbe97d41ccca814cb0b1bb4))


### Documentation

* describe the run as it is now, and add the visual walk-through ([8e55c98](https://github.com/ravensorb/bmad-extensions/commit/8e55c988c5b28e43851052b803dc296433c41390))


### Maintenance

* remove internal identifiers and figures from the published package ([aa68588](https://github.com/ravensorb/bmad-extensions/commit/aa6858898d957d27be9fd089db59e4342c55fc87))

## [2.4.6](https://github.com/ravensorb/bmad-extensions/compare/2.4.5...2.4.6) (2026-08-19)


### Fixes

* **l3io-pm:** make the usage reader resolve and verify whose transcript it read ([45096c3](https://github.com/ravensorb/bmad-extensions/commit/45096c300c5ead2ee3d0af4f04d776dc05d20a90))

## [2.4.5](https://github.com/ravensorb/bmad-extensions/compare/2.4.4...2.4.5) (2026-08-19)


### Features

* **l3io-pm:** add a transcript usage reader, replacing "read the usage fields" ([0cc3f3c](https://github.com/ravensorb/bmad-extensions/commit/0cc3f3c0f33d8479b3c0088965e1355e70b774da))


### Performance

* **l3io-pm:** forbid polling, and scope every reviewer to a diff ([db8383c](https://github.com/ravensorb/bmad-extensions/commit/db8383c3d6c1ae427aa15f5b55e04e2ede60925e))

## [2.4.4](https://github.com/ravensorb/bmad-extensions/compare/2.4.3...2.4.4) (2026-08-19)


### Fixes

* **l3io-pm:** require every technical-AC dimension, and add the library check ([0d5f7f6](https://github.com/ravensorb/bmad-extensions/commit/0d5f7f65a94a73e2fdf84119cbe2f95c9234baf4))


### Performance

* **l3io-pm:** dispatch one agent per story, and cap the fix loop at 3 ([c00dafb](https://github.com/ravensorb/bmad-extensions/commit/c00dafbef77539ba35fe2e11b17a1fd8505adf90))
* **l3io-pm:** stop paying twice for one review, and escalate the arch gate ([da51db2](https://github.com/ravensorb/bmad-extensions/commit/da51db2ad6e0c1ab633f4d0274f703f6dbee9292))

## [2.4.3](https://github.com/ravensorb/bmad-extensions/compare/2.4.2...2.4.3) (2026-08-19)


### Fixes

* **l3io-pm:** measure the tokens_k scope ratio on fresh tokens only ([76c406f](https://github.com/ravensorb/bmad-extensions/commit/76c406f671e03ba36961ceac9a7bc9d8389c3ead))


### CI/CD

* drop the full clone check:version no longer needs ([224d2ca](https://github.com/ravensorb/bmad-extensions/commit/224d2cae4c5c564bb524b0ea17b01c5f918ab8ae))

## [2.4.2](https://github.com/ravensorb/bmad-extensions/compare/2.1.5...2.4.2) (2026-08-18)

## [2.1.5](https://github.com/ravensorb/bmad-extensions/compare/2.1.4...2.1.5) (2026-08-18)


### Fixes

* **l3io-pm:** guard self-install on content, not on a version number ([fa939b7](https://github.com/ravensorb/bmad-extensions/commit/fa939b7438ed5dc9042f643677edfa0aec625d05))

## [2.1.4](https://github.com/ravensorb/bmad-extensions/compare/2.1.3...2.1.4) (2026-08-18)


### Performance

* **l3io-util:** route doctor modes from steps/ instead of inlining them ([c7b87b8](https://github.com/ravensorb/bmad-extensions/commit/c7b87b86928ae81c9e101638004646ba6b2d1692))

## [2.1.3](https://github.com/ravensorb/bmad-extensions/compare/2.1.2...2.1.3) (2026-08-18)


### Features

* **infra:** budget the activation digest ([25072d5](https://github.com/ravensorb/bmad-extensions/commit/25072d53f9bf3f11481d259e60b4b92f7eeb0dbb))
* **infra:** gate the documented metric list and tighten the CLI-surface check ([8592183](https://github.com/ravensorb/bmad-extensions/commit/85921831a15997012597a191a66fb484f7c3a6c0))
* **l3io-pm:** add a model-keyed token rate table and cost derivation ([54f1f1d](https://github.com/ravensorb/bmad-extensions/commit/54f1f1db8d8495ebdfaccfa569fccfb92292464a))
* **l3io-pm:** add hitl_hours, separating supervision time from developer effort ([c3a107d](https://github.com/ravensorb/bmad-extensions/commit/c3a107d475a762054b5e63969cc7485240d20b4a))
* **l3io-pm:** attribute orchestration spend and learn it as a fourth component ([524dd3f](https://github.com/ravensorb/bmad-extensions/commit/524dd3fa8cbe3adc0a18ccc46b6f38cd58e48728))
* **l3io-pm:** break actual spend out by story, closure, and orchestration ([dbaa49d](https://github.com/ravensorb/bmad-extensions/commit/dbaa49d12d0add938b839552969b772be9a0b071))
* **l3io-pm:** close the wait protocol over every spawn site ([3242ef3](https://github.com/ravensorb/bmad-extensions/commit/3242ef345a1333faab00c21c2429a34479c7b5ca))
* **l3io-pm:** derive estimate cost from a banded token total and observed mix ([621f235](https://github.com/ravensorb/bmad-extensions/commit/621f235e78bfea749a6a99144f4a14f6ef4aaaa1))
* **l3io-pm:** make verify recompute cost and enforce the token total invariant ([c0938cf](https://github.com/ravensorb/bmad-extensions/commit/c0938cfdc93412fe8d3327f763802123f0ce5ab1))
* **l3io-pm:** migrate calibration to the new metric shape without a version bump ([b0c5a26](https://github.com/ravensorb/bmad-extensions/commit/b0c5a263632faf8937ca200b3acd2a2f8ac3ce08))
* **l3io-pm:** record dispatch open/close events and flag stalled dispatches ([803fb28](https://github.com/ravensorb/bmad-extensions/commit/803fb28ae4164b8e7bb7df6e41f098398056a5fe))
* **l3io-pm:** roll orchestration overhead into sprint and epic estimates ([828a1e7](https://github.com/ravensorb/bmad-extensions/commit/828a1e77213c844f6b847c3e282b10ee2108b025))
* **l3io-pm:** structure actual tokens by class and derive cost from them ([57afc2f](https://github.com/ravensorb/bmad-extensions/commit/57afc2f7867c2495f4d8d27a5540654e8fdfba54))


### Fixes

* **l3io-pm:** bracket the sprint dispatch and write the real attribution rule ([ae6a8f2](https://github.com/ravensorb/bmad-extensions/commit/ae6a8f2e3cd096dfc0944f4dfd491f80e946d365))
* **l3io-pm:** close the tokens_k mapping blind spot in derive_story_sample ([401b1e8](https://github.com/ravensorb/bmad-extensions/commit/401b1e8c36271a31b1f1a0bb8dc3ba3bfe323ca2))
* **l3io-pm:** close three unfalsifiable-metric holes in set-actual, verify, and report ([6c73e03](https://github.com/ravensorb/bmad-extensions/commit/6c73e03d0d2292a2e34655bb6caaa67d7e85221b))
* **l3io-pm:** compare the closure residual against a tolerance, not exact zero ([765430d](https://github.com/ravensorb/bmad-extensions/commit/765430da031d92806746fd381387682e8fb5f748))
* **l3io-pm:** correct set-actual usage banner and KeyError message quoting ([1b5a8a4](https://github.com/ravensorb/bmad-extensions/commit/1b5a8a42492db3b47a79430c5b8cb269b6b7cbe4))
* **l3io-pm:** gate the metrics migration on a positive marker, not legacy keys ([78fb082](https://github.com/ravensorb/bmad-extensions/commit/78fb082b6fe4828a713be014d4f908517e3b1278))
* **l3io-pm:** guard observed_mix against a non-mapping calibration sample ([273a06e](https://github.com/ravensorb/bmad-extensions/commit/273a06e50d5022fea348bd5de22820f86691d1d2))
* **l3io-pm:** guard the orchestration sample against replay with its own marker ([6a801b5](https://github.com/ravensorb/bmad-extensions/commit/6a801b5a34c8a342ae43207203b4d3f287d1bbfb))
* **l3io-pm:** make set-estimate cost-rejection tests exercise the real path ([70911cd](https://github.com/ravensorb/bmad-extensions/commit/70911cda14f6211424544d577b9d45ae3c247b47))
* **l3io-pm:** make the closure component measure closure, not closure-plus-orchestration ([949349b](https://github.com/ravensorb/bmad-extensions/commit/949349b8a8b79b939d001e11303cf111319feb7a))
* **l3io-pm:** resolve default_model and token_rates, and pass them through ([240b5af](https://github.com/ravensorb/bmad-extensions/commit/240b5afc081b07008de0cafec9e9c4addf67294b))
* **l3io-pm:** route hitl_hours through calibration, not just storage ([66596dd](https://github.com/ravensorb/bmad-extensions/commit/66596dd9f09d91d8a026cc6d00e38e59cbdc32d9))
* **l3io-pm:** sync rate-table payload copies, document rates/dispatch, fix cmd_rates error format ([4128797](https://github.com/ravensorb/bmad-extensions/commit/41287971e350c4e88874fe156367d9d5b5e3c8b3))
* **l3io-pm:** tighten verify's cost tolerance and cover --token-rates wiring ([8cae964](https://github.com/ravensorb/bmad-extensions/commit/8cae964c6c1b63f81c31bd41ed605b153f439376))
* **l3io-util,l3io-pm:** stop two shipped skills reading and writing the retired schema ([e399f76](https://github.com/ravensorb/bmad-extensions/commit/e399f7648a81f3d6a90b86d27a58f6d699b0e174))


### Performance

* **l3io-pm:** batch story enrichment instead of spawning per story ([b01fd3b](https://github.com/ravensorb/bmad-extensions/commit/b01fd3ba36ad30427162f6f67c9d23567880b950))
* **l3io-pm:** let dispatched subagents inherit activation ([0adf95f](https://github.com/ravensorb/bmad-extensions/commit/0adf95f37be44e0a4438f783e7e5e9581f14ff7a))


### Refactoring

* **l3io-pm:** split the calibration model out of the metrics contract ([3e163cb](https://github.com/ravensorb/bmad-extensions/commit/3e163cbe96565855c03d5450dfe1295c2b67c2f2))
* **l3io-pm:** unify estimate time_hours and actual elapsed_hours to one name ([b94fff3](https://github.com/ravensorb/bmad-extensions/commit/b94fff34cb786055a3f59036900a3369e0c310d8))


### Documentation

* **l3io-pm:** add the metrics model rework design and implementation plan ([5ff1e8e](https://github.com/ravensorb/bmad-extensions/commit/5ff1e8e7b1c05db2e4bd10afc93da7d2723d420e))
* **l3io-pm:** document the five-metric model, derived cost, and orchestration ([5c01104](https://github.com/ravensorb/bmad-extensions/commit/5c01104b887a57a255ee125b924fbf578cb4499b))
* **l3io-pm:** fix two factual errors in the metrics contract from review ([9a529d5](https://github.com/ravensorb/bmad-extensions/commit/9a529d57f7b0d5a15d856e6b11bea66f9514e2ca))
* **l3io-pm:** make the no-in-memory-handoff rule operative for subagents ([55e6a45](https://github.com/ravensorb/bmad-extensions/commit/55e6a459296794e0c970b51cf674fbfac664cbb8))
* **l3io-pm:** recompute every cost in the shipped schema examples from the rate card ([c685ee5](https://github.com/ravensorb/bmad-extensions/commit/c685ee50a3d1c31f09045d9aa8faa33e8218a183))


### Maintenance

* **l3io-pm:** bump pm-status.py to 2.4.0 so self-install propagates this fix wave ([8849d34](https://github.com/ravensorb/bmad-extensions/commit/8849d347b683d8b226261632948c647b6c4ca290))

## [2.1.2](https://github.com/ravensorb/bmad-extensions/compare/2.1.1...2.1.2) (2026-08-17)


### Features

* **infra:** check the documented CLI surface and inline config values ([40f573e](https://github.com/ravensorb/bmad-extensions/commit/40f573e42a139d1d06bbacbb2556bf348d24496c))
* **l3io-pm:** filter the progress report by state folder ([88e1417](https://github.com/ravensorb/bmad-extensions/commit/88e14173ae01d182c491a06fe38db75a4f0927a6))

## [2.1.1](https://github.com/ravensorb/bmad-extensions/compare/2.1.0...2.1.1) (2026-08-17)


### Features

* **infra:** gate documentation against the code it describes ([4ad0b1a](https://github.com/ravensorb/bmad-extensions/commit/4ad0b1af0b064535068807471a4cfb7fab4c43ab))
* **l3io-pm:** scale the fix-loop cap to work type ([a1a2438](https://github.com/ravensorb/bmad-extensions/commit/a1a2438e4e621c74733952a23aa61f36fc71cd6f))


### Fixes

* **l3io-pm:** bind max_fix_iterations in headless sprints, drop ATDD refs ([156ee5c](https://github.com/ravensorb/bmad-extensions/commit/156ee5c0b5caf9532cb76cb6c4312afff45b4389))
* **l3io-pm:** correct the activation digest's verify routing and four related nits ([89bf51d](https://github.com/ravensorb/bmad-extensions/commit/89bf51d699a3857fa7b7b7d64b6e322ca8244b51))


### Performance

* **l3io-pm:** add an operative digest to activation ([9f8da53](https://github.com/ravensorb/bmad-extensions/commit/9f8da5395d31fd6e9b35b43ba1fceeb6d04f09d4))
* **l3io-pm:** bound persistent_facts to explicit paths ([82b09c3](https://github.com/ravensorb/bmad-extensions/commit/82b09c3f0a5d761c9495f588c7c5d2f091932f23))
* **l3io-pm:** consult the state and metrics contracts on demand ([70b20f6](https://github.com/ravensorb/bmad-extensions/commit/70b20f6acadd335e6ee1c741987ed79779010d1d))


### Refactoring

* **l3io-pm:** make step-01 the single source of phase gating ([80b64f6](https://github.com/ravensorb/bmad-extensions/commit/80b64f6732bc4e836a29ff7dd354704a760b58ad))


### Documentation

* add a routing table to the digest, and correct the skip_phases claim ([9da2bcd](https://github.com/ravensorb/bmad-extensions/commit/9da2bcdd6517af4c7b305236d3d56757faf4b665))
* add design spec for subagent context trimming ([d0ec251](https://github.com/ravensorb/bmad-extensions/commit/d0ec251e96e464744349c5b9f870f98a2b0ddb8d))
* add implementation plan for phase gating unification ([977e86b](https://github.com/ravensorb/bmad-extensions/commit/977e86b8fe7cf418a1d602ba530e2baa8c46d056))
* add implementation plan for subagent context trimming ([7d8d129](https://github.com/ravensorb/bmad-extensions/commit/7d8d129cdb7fda1ede7005da4f725bebffd47912))
* **l3io-pm:** describe on-demand reference loading, and record the measurement ([7b9c0ca](https://github.com/ravensorb/bmad-extensions/commit/7b9c0cad3e6f93149ab05ebc9aa3e4fd794fe135))
* **l3io-pm:** describe the parallelism that exists, and fix the verify routing row ([6253c18](https://github.com/ravensorb/bmad-extensions/commit/6253c18994f0f0dbe0c73ddd8564efcbc7f633f7))
* reconcile the remaining gating mirrors and fix-cap references ([0b0af23](https://github.com/ravensorb/bmad-extensions/commit/0b0af23e8cc135f0f106c6db4c3516908c03a570))
* spec phase-gating unification (A) and adaptive parallelism (D) ([b68e4f7](https://github.com/ravensorb/bmad-extensions/commit/b68e4f7afeda29f507b82311728854278be9b5cf))

## [2.1.0](https://github.com/ravensorb/bmad-extensions/compare/2.0.4...2.1.0) (2026-08-17)


### Features

* **l3io-pm:** add plan-aware progress reporting ([8191065](https://github.com/ravensorb/bmad-extensions/commit/81910657423e6d6d4727518c3ec0204561fc7bc1))


### Refactoring

* **l3io-pm:** remove the unused progress ledger ([7931dc3](https://github.com/ravensorb/bmad-extensions/commit/7931dc36df0ad91ec0b8956522aa0ab7d81a3cc3))
* **l3io-util:** rename l3io-util-cleanup to l3io-util-doctor ([0085f7a](https://github.com/ravensorb/bmad-extensions/commit/0085f7aed01f01eafa81bc3b8af7e3d40aa4067b))


### Documentation

* consolidate upgrade guidance into docs/upgrading.md ([3e52e1b](https://github.com/ravensorb/bmad-extensions/commit/3e52e1bbc333328d39330a247c36f59e0c80f40d))
* correct the 1.x upgrade path ([a365db5](https://github.com/ravensorb/bmad-extensions/commit/a365db5eb9fbef6f389379b7c6afc3c7d2275bc0))
* refresh all documentation for current skills and progress reporting ([8abc76e](https://github.com/ravensorb/bmad-extensions/commit/8abc76ecf903d734333c51d2fe0c897c19a6acf7))

## [2.0.4](https://github.com/ravensorb/bmad-extensions/compare/2.0.3...2.0.4) (2026-08-17)


### Fixes

* **l3io-pm:** make the plan snapshot's authority explicit and stop duplicating phases ([e42bc66](https://github.com/ravensorb/bmad-extensions/commit/e42bc66376652913bdea5cfaec40c27a9e38f85a))

## [2.0.3](https://github.com/ravensorb/bmad-extensions/compare/2.0.2...2.0.3) (2026-08-17)


### Fixes

* **l3io-pm:** guard execute against stale plans instead of corrupting epic state ([dd542f9](https://github.com/ravensorb/bmad-extensions/commit/dd542f9f0c4bcf09ec090d9637e56f9148dc6c70))

## [2.0.2](https://github.com/ravensorb/bmad-extensions/compare/2.0.1...2.0.2) (2026-08-16)


### Features

* **l3io-pm:** add calibration file I/O and calibration show ([1e7f670](https://github.com/ravensorb/bmad-extensions/commit/1e7f6706c3d4e31f60eafbe1f4f66265c63a6097))
* **l3io-pm:** add estimate-rollup and bump pm-status.py to 2.1.0 ([d55598a](https://github.com/ravensorb/bmad-extensions/commit/d55598a4185e108f0d8b5cb027b5667d3cc77b53))
* **l3io-pm:** add estimate-story ([7c772cd](https://github.com/ravensorb/bmad-extensions/commit/7c772cd22c62c08151936af6a8c871acbd39ce73))
* **l3io-pm:** derive closure calibration samples ([ccb251e](https://github.com/ravensorb/bmad-extensions/commit/ccb251e8452b949c02cf113648f641c86cb734cc))
* **l3io-pm:** derive story calibration samples ([de52f89](https://github.com/ravensorb/bmad-extensions/commit/de52f89baafe1fe17822ee7078879fb08b4480a2))
* **l3io-pm:** emit calibration samples from set-actual ([498e242](https://github.com/ravensorb/bmad-extensions/commit/498e2421db5aced3b0c61d0c480e9f799bb4f141))
* **l3io-pm:** record fix_factor and scope_ratio on estimates ([7b03d53](https://github.com/ravensorb/bmad-extensions/commit/7b03d53c3545c4fb0b1ad63c39eb3e0f11d95cf6))


### Fixes

* **infra:** resolve config through BMad core instead of a file BMad never creates ([deb1827](https://github.com/ravensorb/bmad-extensions/commit/deb18273b96ffc2e872e0d80f033293d82c3afb2))
* **l3io-pm:** correct the calibration loop so it converges to truth ([1477fe7](https://github.com/ravensorb/bmad-extensions/commit/1477fe77958b4620aa2549f6ce7bf4bd4f0661d2))
* **l3io-pm:** elaborate stories in place instead of spawning bmad-create-story ([6b6abb9](https://github.com/ravensorb/bmad-extensions/commit/6b6abb903df32d720088d9f25a9154787db6f89d))
* **l3io-pm:** parse $-prefixed cost before the numeric guard ([d9b47cc](https://github.com/ravensorb/bmad-extensions/commit/d9b47cc02453e84d706bf85680620b6a74a21b49))


### Documentation

* add calibration mechanization design spec ([4cee74d](https://github.com/ravensorb/bmad-extensions/commit/4cee74da61a0bd14884177934f9898ef098ce674))
* add calibration mechanization implementation plan (8 tasks) ([a7aff09](https://github.com/ravensorb/bmad-extensions/commit/a7aff09f3b84cc2dbad4ac89fb590cff6af76230))
* bring architecture.md and l3io-pm-reference.md up to the current design ([06e206d](https://github.com/ravensorb/bmad-extensions/commit/06e206de2a0dc555ab97dd25c338dbd5869ac797))
* **l3io-pm:** complete the dependency table and record declared-vs-invoked gaps ([50ff082](https://github.com/ravensorb/bmad-extensions/commit/50ff082cd950c8cdd266f794f90a4f31fefce7de))
* **l3io-pm:** correct the QA row — no QA phase is actually invoked ([192cc89](https://github.com/ravensorb/bmad-extensions/commit/192cc8904d8d23c6dca8dda9d9ac0f5f510cd6b5))
* **l3io-pm:** document the calibration loop that now runs ([cdaf550](https://github.com/ravensorb/bmad-extensions/commit/cdaf550e55115a734058258b1e16730488bc370d))
* **l3io-pm:** fix false fix-factor claim in calibration worked example ([79b1959](https://github.com/ravensorb/bmad-extensions/commit/79b1959b4b818a846ad3cf3094443e96e4144c2e))
* **l3io-pm:** fix two stale references surfaced during the create-story review ([7f13b66](https://github.com/ravensorb/bmad-extensions/commit/7f13b660b48306424750107fda425b00704df542))

## [2.0.1](https://github.com/ravensorb/bmad-extensions/compare/2.0.0...2.0.1) (2026-08-16)


### Features

* **l3io-pm:** add list-issues subcommand to pm-status.py ([433bc30](https://github.com/ravensorb/bmad-extensions/commit/433bc30159b45523b536b0bf1ffe723ab5a38e9c))
* **l3io-pm:** resolve state nodes by key over a sharded tree ([8d3d2c2](https://github.com/ravensorb/bmad-extensions/commit/8d3d2c29fdea90b5ac1c4bce949bbdafba633857))


### Fixes

* **ci-cd:** update test path to skills/_shared/ for v2 flat layout ([9d7f6f5](https://github.com/ravensorb/bmad-extensions/commit/9d7f6f5110bf177f7bb60965814f7a5f70ecd7c2))
* **infra:** document the sharded layout and gate releases on script sync ([eb9a24f](https://github.com/ravensorb/bmad-extensions/commit/eb9a24f533522aec43110cc0a5768bbb2cd64207))
* **l3io-pm:** bind {runtime} at activation for set-actual/verify calls ([c81f748](https://github.com/ravensorb/bmad-extensions/commit/c81f7480131f164e9e481740d30192e91eac85f5))
* **l3io-pm:** call pm-status.py with keys, and fix the upgrade deadlock ([f511f1d](https://github.com/ravensorb/bmad-extensions/commit/f511f1d749c3bb29483dc931bcbcc5422485a8df))
* **l3io-pm:** close upgrade-path gaps in migration, help, and state helper ([6f01f2c](https://github.com/ravensorb/bmad-extensions/commit/6f01f2c39cdaa92bcec54954a2f3afea86453764))
* **l3io-pm:** gate module setup on state being version-controlled ([1cfaa73](https://github.com/ravensorb/bmad-extensions/commit/1cfaa738b78c30706e3268fe3173078c6ec5ebe8))
* **l3io-pm:** read the sharded layout in l3io-pm-help ([e428d58](https://github.com/ravensorb/bmad-extensions/commit/e428d583c08140b8d091f00826085f7fcd0a02c0))
* **l3io-pm:** remove dead deferred epic-status bucket from l3io-pm-plan ([1c28bba](https://github.com/ravensorb/bmad-extensions/commit/1c28bba4fcfa9a00c3e7f7f4fd9ca62f98b3791e))
* **l3io-pm:** repair l3io-pm-sync against its real script CLIs ([890c748](https://github.com/ravensorb/bmad-extensions/commit/890c7482423fc50950342c266cc619995c303215))
* **l3io-util:** extend clean-legacy to cover migrate-state's actual backups ([0add27d](https://github.com/ravensorb/bmad-extensions/commit/0add27dcb768bdbeaa7416f9b45e6c7f6efdce5a))
* **l3io-util:** migrate to the sharded layout, verify before destroying ([0718ab6](https://github.com/ravensorb/bmad-extensions/commit/0718ab6783f948b3e44d939a0066973b0d4bdb3c))


### Documentation

* add design spec and implementation plan for state relocation ([845495a](https://github.com/ravensorb/bmad-extensions/commit/845495a71176b00956e777024fb68c16bdd796aa))
* **l3io-pm:** add metrics-contract.md reference and wire into shared sync ([93c7db0](https://github.com/ravensorb/bmad-extensions/commit/93c7db0b132fe0dccbcc8c49a801d760b4525c2d))
* **l3io-pm:** correct stale pm-status.py help text ([d11c359](https://github.com/ravensorb/bmad-extensions/commit/d11c3591acd3146e772143e9dc5183b72de11faa))
* **l3io-pm:** rewrite status-files.md as the state layout contract ([c188377](https://github.com/ravensorb/bmad-extensions/commit/c188377ea6981592ad8abb74e9157a9df862ec3b))

## [2.0.0](https://github.com/ravensorb/bmad-extensions/compare/1.1.1...2.0.0) (2026-08-15)


### Features

* **infra:** add pm-status.py v2.0.0 with lock, field, issue, and archive subcommands ([6ea1be7](https://github.com/ravensorb/bmad-extensions/commit/6ea1be7fc3b3a86620581b8d2fbc5e090f88cdb5))
* **infra:** add resolve_config.py and memlog.py runtime scripts ([957bb45](https://github.com/ravensorb/bmad-extensions/commit/957bb4552e4bc5755754d93bd5cabfa9a7e8eff3))
* **infra:** add shared step files for all PM skill categories ([d3af128](https://github.com/ravensorb/bmad-extensions/commit/d3af128a46bb6c6a3918c0711d6846d225b6593d))
* **infra:** add updated status-files.md for _bmad/state/ layout ([61301f5](https://github.com/ravensorb/bmad-extensions/commit/61301f571d27a5ee312ce9969d0fcc9157dda381))
* **infra:** rewrite sync-shared-scripts.mjs for skills/ flat layout and new script manifest ([64b9a78](https://github.com/ravensorb/bmad-extensions/commit/64b9a782c8f88649556e2b1a89717765cef3a1d3))
* **l3io-pm:** add l3io-pm-execute skill (merged sprint+epic execution) ([7576731](https://github.com/ravensorb/bmad-extensions/commit/7576731a625990851ada84a18fd6715a72a56eb3))
* **l3io-pm:** add l3io-pm-help skill (state snapshot + next-action recommendation) ([db75104](https://github.com/ravensorb/bmad-extensions/commit/db75104279749c6528136ade6d3c4b5d621bdb18))
* **l3io-pm:** add l3io-pm-plan skill (renamed from plan-execution, steps architecture) ([1dd2383](https://github.com/ravensorb/bmad-extensions/commit/1dd238322f143f8238c5be92a6e3c8454a55efa3))
* **l3io-pm:** add l3io-pm-sync skill (GitHub Issues bidirectional sync) ([15c42f9](https://github.com/ravensorb/bmad-extensions/commit/15c42f9b884ef88f4f8403162538f8972a44b351))
* **l3io-sec:** rename l3io-sec-agent-redteam → l3io-sec-redteam (flat layout) ([5ac4870](https://github.com/ravensorb/bmad-extensions/commit/5ac487019308bf73240e1a0534def6576dad765a))
* **l3io-util:** add migrate-state mode and 9-check health check to util-cleanup ([8653080](https://github.com/ravensorb/bmad-extensions/commit/865308096f627ec844aa5efd7c30f7536ab76605))


### Fixes

* **infra:** patch brace-expansion DoS vulnerability in lockfile ([de2eaf5](https://github.com/ravensorb/bmad-extensions/commit/de2eaf50ba210ac8594c978b0e0518d631b80ef4))
* **infra:** rename {ava_key} → {story_key} in sync step-04-resolve.md ([eb53540](https://github.com/ravensorb/bmad-extensions/commit/eb53540e0fa9c98ca5073214222675d25e59f299))
* **infra:** update stale sprint-execute/epic-execute refs in CLAUDE.md to l3io-pm-execute ([c3bf2f3](https://github.com/ravensorb/bmad-extensions/commit/c3bf2f34359c6c134257bf68be8df7d45e0fa1d2))
* **infra:** use key: schema in primary SAMPLE fixture for pm-status tests ([72ae464](https://github.com/ravensorb/bmad-extensions/commit/72ae464de0d8c7010eb72e78be4a21b88a52773b))
* **l3io-pm:** remove ADO reference from sync module-help.csv description ([1373d82](https://github.com/ravensorb/bmad-extensions/commit/1373d82c0b99e5852fcb93a89cdb3906494bc000))
* **l3io-sec:** correct SKILL_NAME in init-sanctum.py (remove bmad- prefix) ([1aed23d](https://github.com/ravensorb/bmad-extensions/commit/1aed23db23fac8128e36e209f0a3e469e02e5958))


### Documentation

* add v2.0.0 migration design spec ([f272419](https://github.com/ravensorb/bmad-extensions/commit/f2724196acfab6530f25aaf9e6051e887b27b143))
* add v2.0.0 migration implementation plan (14 tasks) ([6651997](https://github.com/ravensorb/bmad-extensions/commit/66519976a774990cf334dd5a39120e6f41c906ee))
* complete v2.0.0 design spec with full gap analysis ([0e3ae74](https://github.com/ravensorb/bmad-extensions/commit/0e3ae747af9db6a61ba1ccd70350a98f27ca468c))
* show full tools list in upgrade command ([93a40ad](https://github.com/ravensorb/bmad-extensions/commit/93a40ad0ad947f0a73497a4b67c52f22fd409c8d))
* simplify upgrade to a single explicit one-liner with no prompts ([9c138f3](https://github.com/ravensorb/bmad-extensions/commit/9c138f3e1b9247106f76520fb38388cf455091da))
* simplify upgrade to quick-update one-liner ([0adbd85](https://github.com/ravensorb/bmad-extensions/commit/0adbd8598aa711cc4df2dd34485c44f4241eb369))
* update migration plan with post-2.0.0 fixes from reference (2.0.1-2.0.4) ([3361f8c](https://github.com/ravensorb/bmad-extensions/commit/3361f8c619930075dc243d879e4b07387aa35122))


### Maintenance

* **infra:** update symlinks, marketplace.json, and CLAUDE.md for flat skills/ layout ([62a2def](https://github.com/ravensorb/bmad-extensions/commit/62a2def534feabd3d7a83d187069abf169b4fa55))
* **l3io-arch:** move l3io-arch-review to flat skills/ layout ([cd61296](https://github.com/ravensorb/bmad-extensions/commit/cd61296da459f2caec6532f62f3e436343aa7102))
* remove src/ — all skills migrated to flat skills/ layout ([1a23e74](https://github.com/ravensorb/bmad-extensions/commit/1a23e749923fb308a8fe0dfc55e5bd527f69bf2d))

## [1.1.1](https://github.com/ravensorb/bmad-extensions/compare/1.1.0...1.1.1) (2026-07-31)


### Features

* **infra,l3io-pm:** move _shared/ to repo-level src/_shared/ and align with avanade ([f47e7f3](https://github.com/ravensorb/bmad-extensions/commit/f47e7f39526c3d71a443c05f3f462bf04171e32b))

## [1.1.0](https://github.com/ravensorb/bmad-extensions/compare/1.0.28...1.1.0) (2026-07-31)

## [1.0.28](https://github.com/ravensorb/bmad-extensions/compare/1.0.27...1.0.28) (2026-07-31)


### Features

* **l3io-pm,l3io-arch:** pre-execution epic arch gate + story technical-AC gate ([542e092](https://github.com/ravensorb/bmad-extensions/commit/542e092a1e77a7de98cc472ff9db0ddcff008c25))
* **l3io-pm:** add shared atomic pm-status.py status/progress helper ([2beab1e](https://github.com/ravensorb/bmad-extensions/commit/2beab1e30f488aff928e51508853ca6eb8cabc30))
* **l3io-pm:** route status/actuals/progress through pm-status.py; auto parallelism ([a66c433](https://github.com/ravensorb/bmad-extensions/commit/a66c433ec05bfb6654c8a4ff97febdc47c5dac4e))


### Fixes

* **l3io-pm:** harden token/cost capture across nested subagent runs ([a583a8e](https://github.com/ravensorb/bmad-extensions/commit/a583a8eba2c1b1468a2d8eee395091885eadea36))


### Documentation

* **l3io-pm:** document reliability/quality changes and shared-helper model ([bfb402a](https://github.com/ravensorb/bmad-extensions/commit/bfb402a7a379740d495dae346b542ae2e5d6e474))

## [1.0.27](https://github.com/ravensorb/bmad-extensions/compare/1.0.26...1.0.27) (2026-07-08)


### Features

* **l3io-arch:** add architecture standards module ([86643c1](https://github.com/ravensorb/bmad-extensions/commit/86643c1ef5090acaa681e112212fa1bdb0b0dccf))
* **l3io-pm:** add optional ATDD scaffold phase to sprint story loop ([5f7b1f6](https://github.com/ravensorb/bmad-extensions/commit/5f7b1f65107cbf8b27bf9e503ca842adb1c988e1))


### Documentation

* cover both Claude Code and GitHub Copilot in install/upgrade ([1ec91e0](https://github.com/ravensorb/bmad-extensions/commit/1ec91e0323464c150dcee01e12fafe2f14111f42))
* drop folded-in *-setup skills from Modules table ([4355698](https://github.com/ravensorb/bmad-extensions/commit/43556984aac7047eb02da209aa4cf942158d9857))
* **l3io-arch:** document new module and fix stale module docs ([fa217c1](https://github.com/ravensorb/bmad-extensions/commit/fa217c156f8f4e34c7e7db0c32b945da13c4929b))
* **l3io-sec:** name GitHub Copilot explicitly in module.yaml discovery note ([e6f6bdb](https://github.com/ravensorb/bmad-extensions/commit/e6f6bdb3a2e3eaec57ebc46b38fd47100c6f3c2b))

## [1.0.26](https://github.com/ravensorb/bmad-extensions/compare/1.0.25...1.0.26) (2026-07-05)


### Fixes

* **l3io-pm,l3io-sec,l3io-util:** add top-level module.yaml for installer discovery ([5fb58fa](https://github.com/ravensorb/bmad-extensions/commit/5fb58fa5a832a6ab60984063f4e80595a24d1bec))

## [1.0.25](https://github.com/ravensorb/bmad-extensions/compare/1.0.24...1.0.25) (2026-07-01)


### Refactoring

* embed module setup in operational skills; remove standalone setup skills ([8ce9a23](https://github.com/ravensorb/bmad-extensions/commit/8ce9a23fed6656a8fc189239c683d1a8e58773d1))

## [1.0.24](https://github.com/ravensorb/bmad-extensions/compare/1.0.23...1.0.24) (2026-07-01)


### Features

* **l3io-util:** add help, stats, backlog, normalize, clean-legacy modes; reorganize command structure ([a35bee9](https://github.com/ravensorb/bmad-extensions/commit/a35bee9d76fd27475b1c2b22faf60f8fbee520b3))

## [1.0.23](https://github.com/ravensorb/bmad-extensions/compare/1.0.22...1.0.23) (2026-06-29)


### Features

* **l3io-util:** add reconcile-status mode to l3io-util-cleanup ([9244bd8](https://github.com/ravensorb/bmad-extensions/commit/9244bd851b710297b5b4961a908ad76cdfee773e))

## [1.0.22](https://github.com/ravensorb/bmad-extensions/compare/1.0.21...1.0.22) (2026-06-27)


### Features

* **l3io-pm,l3io-util:** redesign backlog item lifecycle and key format ([38c9ccf](https://github.com/ravensorb/bmad-extensions/commit/38c9ccf272f387b77d42d54575ec2fb0574f5b13))

## [1.0.21](https://github.com/ravensorb/bmad-extensions/compare/1.0.20...1.0.21) (2026-06-27)


### Features

* **l3io-util:** health-check default mode for l3io-util-cleanup ([3877483](https://github.com/ravensorb/bmad-extensions/commit/38774832ae0c0d78e2db5fb9f0851efbcaf0cdfe))


### Documentation

* update README with upgrade section and fix sprint-status naming ([feea90d](https://github.com/ravensorb/bmad-extensions/commit/feea90d50fc2dd444629c4bfb10177c211d167aa))

## [1.0.20](https://github.com/ravensorb/bmad-extensions/compare/1.0.19...1.0.20) (2026-06-27)


### Features

* **l3io-pm,l3io-util:** rename sprint-status-active.yaml → sprint-status.yaml ([8682833](https://github.com/ravensorb/bmad-extensions/commit/8682833648319dd1f852a2f8d8f84d2874ff4c05))

## [1.0.19](https://github.com/ravensorb/bmad-extensions/compare/1.0.18...1.0.19) (2026-06-26)


### Features

* **l3io-util:** update-ai-rules mode + migrate-schema split layout + Step 6/7 fixes ([17f8f22](https://github.com/ravensorb/bmad-extensions/commit/17f8f22b4f712dbb780af20eef08b8dc889b3704))

## [1.0.18](https://github.com/ravensorb/bmad-extensions/compare/1.0.17...1.0.18) (2026-06-26)


### Fixes

* **l3io-pm:** consolidate module registry into setup skill to fix sprint install ([358b670](https://github.com/ravensorb/bmad-extensions/commit/358b6704a7a094485e28a7e6af0e2148d15fbace))

## [1.0.17](https://github.com/ravensorb/bmad-extensions/compare/1.0.16...1.0.17) (2026-06-26)


### Features

* **l3io-pm,l3io-util:** status validation gates + sort-status mode ([7f41d07](https://github.com/ravensorb/bmad-extensions/commit/7f41d073f966948988a9a618902533ce3903d493))

## [1.0.16](https://github.com/ravensorb/bmad-extensions/compare/1.0.15...1.0.16) (2026-06-25)


### Features

* **l3io-pm:** bottom-up estimate roll-up + decomposed scope/closure/fix calibration ([b0f4df5](https://github.com/ravensorb/bmad-extensions/commit/b0f4df5000d4f4082818bf5ceee94eaa1ec6e596))

## [1.0.15](https://github.com/ravensorb/bmad-extensions/compare/1.0.14...1.0.15) (2026-06-25)


### Fixes

* **l3io-pm,l3io-sec,l3io-util:** rename module-help.csv header after,before to preceded-by,followed-by ([b7e9fb8](https://github.com/ravensorb/bmad-extensions/commit/b7e9fb88eacba270b5a39da6ec214165a4c8c507))

## [1.0.14](https://github.com/ravensorb/bmad-extensions/compare/1.0.13...1.0.14) (2026-06-25)


### Features

* **l3io-pm,l3io-sec,l3io-util:** rename skills to l3io-* prefix; scaffold setup skills; wire first-run auto-config ([b91ed6f](https://github.com/ravensorb/bmad-extensions/commit/b91ed6fcd7e5fc2b1b4345782bae812b3dd64e02))

## [1.0.13](https://github.com/ravensorb/bmad-extensions/compare/1.0.12...1.0.13) (2026-06-25)


### Fixes

* **l3io-pm,l3io-util:** fix dedupe contract, announce counts, and loop header clarity ([6e10f44](https://github.com/ravensorb/bmad-extensions/commit/6e10f4487b17fe2ad393e835821aef63db849406))

## [1.0.12](https://github.com/ravensorb/bmad-extensions/compare/1.0.11...1.0.12) (2026-06-22)


### Features

* **l3io-pm:** leanness cut-list + bmad-defer harvest in sprint closure ([d6a8183](https://github.com/ravensorb/bmad-extensions/commit/d6a8183a74fe8b78bb5a262a0d8686f4f2f54755))
* **l3io-util:** add harvest-debt mode for bmad-defer code markers ([9f2c07b](https://github.com/ravensorb/bmad-extensions/commit/9f2c07b4d6eda619e950ded04bbd48a6a39f59e9))


### Documentation

* **l3io-pm:** align reference + getting-started with 1.0.9–1.0.11 features ([bcce91e](https://github.com/ravensorb/bmad-extensions/commit/bcce91e5e8a50b82b361d2fe165173a09fb923be))

## [1.0.11](https://github.com/ravensorb/bmad-extensions/compare/1.0.10...1.0.11) (2026-06-15)


### Features

* **l3io-pm:** split sprint-status.yaml into active/backlog/archived state files ([eb879ef](https://github.com/ravensorb/bmad-extensions/commit/eb879ef7cb1ab4981daf98cf1c968280291b134f))


### Fixes

* **l3io-pm:** scope token/cost capture by session id, not cwd ([5b9ea56](https://github.com/ravensorb/bmad-extensions/commit/5b9ea560225d0d11d3b3982b5aede2d4fef3a7dc))


### Maintenance

* **infra:** align commit scope list with actual module scopes ([98feb0c](https://github.com/ravensorb/bmad-extensions/commit/98feb0c3381226f417fc47ae88a8847ad0e708d5))

## [1.0.10](https://github.com/ravensorb/bmad-extensions/compare/1.0.9...1.0.10) (2026-06-13)


### Features

* **l3io-pm:** enforce estimates + actuals hard rule with runtime-aware metric capture ([57236d3](https://github.com/ravensorb/bmad-extensions/commit/57236d3999273aaa408c68b38f75aaba49ade511))

## [1.0.9](https://github.com/ravensorb/bmad-extensions/compare/1.0.8...1.0.9) (2026-05-28)


### Features

* **l3io-pm:** add estimation calibration from plan-vs-actual sprint history ([cf5ec00](https://github.com/ravensorb/bmad-extensions/commit/cf5ec00643deb454ea5488479b0b51dd0eca130b))

## [1.0.8](https://github.com/ravensorb/bmad-extensions/compare/1.0.7...1.0.8) (2026-05-28)


### Fixes

* **infra:** stage sync output files in postbump so release picks them up ([27a90b6](https://github.com/ravensorb/bmad-extensions/commit/27a90b6bc7416cb4d79a94c4affdb50f34520edf))


### Documentation

* **l3io-pm:** update reference and getting-started for new schema and migrate-schema ([9a328dc](https://github.com/ravensorb/bmad-extensions/commit/9a328dcec6fd06a67ae99d95d93bf678579900ad))


### Maintenance

* merge remote 1.0.6 release branch into local history ([45399eb](https://github.com/ravensorb/bmad-extensions/commit/45399eb23b79fc28c8e62889f7b95f4e3c32e8a5))
* **release:** 1.0.6 ([5d1b7c5](https://github.com/ravensorb/bmad-extensions/commit/5d1b7c56c45c57a0dec27e62e5a835340ae43256))

## [1.0.7](https://github.com/ravensorb/bmad-extensions/compare/1.0.5...1.0.7) (2026-05-28)


### Features

* **l3io-pm:** enrich sprint-status.yaml schema with estimates, actuals, and classification tracking ([abb7390](https://github.com/ravensorb/bmad-extensions/commit/abb7390943e783b98b0407ef5c9a8561f6b859c7))
* **l3io-util:** add migrate-schema mode to bmad-l3io-util-cleanup ([a93e8d8](https://github.com/ravensorb/bmad-extensions/commit/a93e8d8f2c28bfe11c258554a9bded1a9c3c79a8))


### Fixes

* **custom:** align module-help.csv headers with canonical schema ([6284eeb](https://github.com/ravensorb/bmad-extensions/commit/6284eeb08cdf083030dd95aa7f2ec4bf0c683243))


### Maintenance

* fix postbump hook and sync marketplace versions to 1.0.6 ([a74c216](https://github.com/ravensorb/bmad-extensions/commit/a74c2166e8bb662123a9cd637ff05cb148458e3c))
* **release:** 1.0.6 ([2d98fde](https://github.com/ravensorb/bmad-extensions/commit/2d98fde4dea8a902ae6b1356ee0cc4c764868d7a))

## [1.0.6](https://github.com/ravensorb/bmad-extensions/compare/1.0.5...1.0.6) (2026-05-27)


### Features

* **l3io-pm:** enrich sprint-status.yaml schema with estimates, actuals, and classification tracking ([35eb644](https://github.com/ravensorb/bmad-extensions/commit/35eb64478ec09947517acb24450b0ed5de8eca4c))

## [1.0.5](https://github.com/ravensorb/bmad-extensions/compare/1.0.4...1.0.5) (2026-05-27)


### Fixes

* **l3io-pm:** detect redteam skill in .claude/skills as well as .claude/commands ([7f9c93f](https://github.com/ravensorb/bmad-extensions/commit/7f9c93f157ccb6d9590e12be4996d2461fbd8ebc))

## [1.0.4](https://github.com/ravensorb/bmad-extensions/compare/1.0.3...1.0.4) (2026-05-25)


### Features

* **l3io-pm:** add cicd-guidelines reference with multi-runner pipeline conventions ([85a409f](https://github.com/ravensorb/bmad-extensions/commit/85a409f68a8adc7d9b55df1044ef4fdc0dd25cf4))
* **l3io-pm:** add cost estimates at story, sprint, and epic level ([5a64af9](https://github.com/ravensorb/bmad-extensions/commit/5a64af9f207807c25f904fb600ec1e16da17672c))
* **l3io-pm:** propagate deferred-cleanup instruction to all subagent prompts ([7318c63](https://github.com/ravensorb/bmad-extensions/commit/7318c63180b7e663593d49495e5dc562e55ef78f))

## [1.0.3](https://github.com/ravensorb/bmad-extensions/compare/1.0.2...1.0.3) (2026-05-17)


### Features

* **l3io-pm:** add epic backlog file accumulation to sprint closure ([2e7da85](https://github.com/ravensorb/bmad-extensions/commit/2e7da856269e27577f4f96545238acd4e025a601))
* **l3io-pm:** add optional deferred file cleanup to batch rm at sprint/epic close ([a630713](https://github.com/ravensorb/bmad-extensions/commit/a630713393c93f50c96390d2db520b5258789534))
* **l3io-util:** enhance cleanup with recursive scan, deferred work tracking, and completeness loop ([9ddda11](https://github.com/ravensorb/bmad-extensions/commit/9ddda115b32b31e11f9377c78408d33f3476af1f)), closes [#5](https://github.com/ravensorb/bmad-extensions/issues/5)


### Maintenance

* bump all module versions to 1.0.3 ([30ec22b](https://github.com/ravensorb/bmad-extensions/commit/30ec22b35d9f04b9d77447c4617c0ba236bcc928))

## 1.0.2 (2026-05-16)

### Features

* **l3io-pm**: cut interactive prompts during sprint and epic execution. The orchestrators now run end-to-end with minimal user intervention; the only remaining interactive prompt in normal flow is the sprint scope confirmation when a sprint is launched **manually** (sprints spawned by epic-execute run headlessly with no confirmation).

### Behavior changes

* **Per-story fix loop cap raised from 3 → 10 iterations.** Loop runs fix → QA → re-check autonomously; only halts and prompts `{user_name}` if 10 iterations still leave issues unresolved.
* **Quality gate now includes Medium severity.** Sprint and epic closure require all Critical, High, and Medium findings to be resolved (previously: Critical + High only). Low findings auto-defer to backlog with no prompt.
* **Closure fix loop added** (sprint and epic): same 10-iteration cap. Findings are auto-triaged to fix-now (Critical/High/Medium + undocumented drift + functional AC gaps) vs. defer-to-backlog (Low) and processed without per-item user prompts.
* **Removed prompts:** per-story prep checkpoint, between-sprint pause in epic execution, UX-spec-not-found ask (now auto-SKIP when no UX specs are found).
* **HALT prompts now include estimates** (time + tokens per option) so `{user_name}` can decide informed when the 10-iteration cap is hit.

## 1.0.1 (2026-05-16)

### Fixes

* **install:** silence `collectAgentsFromModuleYaml` and `writeCentralConfig` warnings during install by restructuring to the canonical BMad community module layout — `src/<module>/module.yaml` + `src/<module>/module-help.csv` at each module root, with skills nested as `src/<module>/bmad-l3io-<skill>/`. Agents declared in `module.yaml` now register correctly in the consumer's `config.toml` and user-scoped prompt keys file to `config.user.toml` as intended.

### Refactoring

* **infra:** rename all skills with `bmad-` prefix (SKILL-04 compliance): `bmad-l3io-pm-sprint-execute`, `bmad-l3io-pm-epic-execute`, `bmad-l3io-sec-agent-redteam`, `bmad-l3io-util-cleanup`. Slash commands change accordingly (`/bmad-l3io-pm-sprint-execute`, etc.).
* **infra:** move from flat `skills/` layout to per-module `src/<module>/` subtrees so PluginResolver Strategy 1 (root module files) fires cleanly for each plugin.
* **l3io-sec:** strip `name:` / `description:` frontmatter from `references/*.md` files (bmad-method validator rules WF-01/WF-02 reserve those fields for `SKILL.md` only). `CAPABILITIES.md` is now populated from the hand-curated `assets/CAPABILITIES-template.md` instead of being auto-generated from reference frontmatter.

### Notes

* Slash command names change from `/l3io-*` to `/bmad-l3io-*` — re-install in consumer repos picks up the new symlinks.
* Module names (`l3io-pm`, `l3io-sec`, `l3io-util`) and module codes are unchanged.

## 1.0.0 (2026-05-16)

Initial release of `bmad-l3io-extensions` — three installable BMad community modules for sprint/epic delivery, security review, and artifact organization.

### Features

* **l3io-pm**: sprint and epic execution orchestration
  * `bmad-l3io-pm-sprint-execute`: per-story prep → dev → code review → QA → fix loop, then closure (retro, clean release, adversarial, red team, UX, arch drift, issue triage). Sprint cannot close until all Critical/High findings are resolved.
  * `bmad-l3io-pm-epic-execute`: sprint grouping → sprint execution loop → epic-level closure (retro, parallel review batch, arch drift, functional completeness, issue triage). Epic cannot close until all Critical/High findings and undocumented drift are resolved.
* **l3io-sec**: memory-backed red team security agent (`bmad-l3io-sec-agent-redteam`) — adversarial review across five threat lenses (EXT, INS, CHA, ABU, DAR) with an AI poisoning cross-cut (AIP) and live cloud/platform best practices research (PBR). Persists a per-project sanctum with research cache.
* **l3io-util**: one-time artifact migration utility (`bmad-l3io-util-cleanup`) that reorganizes flat BMad artifacts into the standard `epic-XX/sprint-YY` folder layout with zero-padded names and reference reconciliation.

### Execution model

* Each phase runs in a fresh subagent — all state passes through disk, never through in-memory hand-off.
* Adaptive parallelism: defaults to sequential, hard cap of 4 concurrent subagents when independence and state safety can be verified.
* Quality gates: sprint and epic closure require all Critical and High severity findings to be resolved.
