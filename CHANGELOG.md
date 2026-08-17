# Changelog

All notable changes to this project will be documented in this file. See [commit-and-tag-version](https://github.com/absolute-version/commit-and-tag-version) for commit guidelines.

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
