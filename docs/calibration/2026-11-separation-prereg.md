# Separation test: pre-registration

This public copy is edited to remove private names, and its timing cannot be checked from this fork's single commit. Written and committed before any score of the frozen rule set was produced on the human repos, the agent repos
or the hold-out (the exceptions are disclosed in "What was seen before this commit").

**Question.** At the frozen rules, is the ast-only share of code written by agents higher than that of
human-written TypeScript React/Next.js applications from before coding agents?

## Frozen tool and rules

- The fork at the commit that froze the rule set after relabelling. 27 TS rules, `--profile ts`. No rule, threshold or profile change after it in this stage.
- Per-repo command: `scb-check check <paths> --profile ts --strict-sg --report`, run with the repo root as the working directory
  (the walker matches the profile's excludes relative to it). Hits and per-rule counts come from `scripts/separation_score.py`, which calls
  `analyze_paths` with `PROFILES["ts"]` and `strict_sg=True`, the same call as `scripts/calibrate_rules.py`.

## Human group (selection rule, applied before any score)

Exactly 4 public TypeScript React or Next.js application repos, permissive licence, each at its **last commit on the default
branch before 2021-06-01T00:00:00Z** (GitHub API `commits?until=`), each at least 5,000 SLOC under `--profile ts`, at least 40,000 SLOC in total.

Candidate order: GitHub search `topic:react` or `topic:nextjs`, `language:TypeScript`, `created:<2021-03-01`, licences mit, apache-2.0, bsd-3-clause, isc,
`stars:>3000`, sorted by stars descending. Libraries, frameworks, toolkits and monorepo tooling are not applications and are skipped. Walk the
applications in that order. Accept a candidate when, at its pre-June-2021 commit: (a) `.ts`/`.tsx` files are at least half of the tracked
`.ts/.tsx/.js/.jsx` files (so it is a TypeScript repo at that date, not only today), and (b) SLOC under `--profile ts` is at least 5,000. Stop at 4 accepted.
SLOC is the tool's `total_loc`; `--profile ts` also scans any `.js` files, which count (all four have some). The size check printed only `total_loc`
and a skipped-file count.

| Order | Repo | Licence | Commit (last before 2021-06-01) | Commit date | `.ts/.tsx` : `.js/.jsx` files | SLOC | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | freeCodeCamp/freeCodeCamp | BSD-3-Clause | c0feae045969e33324c6874f4a995433e5aa56ad | 2021-05-31 | 6 : 610 | not measured | rejected: JavaScript at that date (rule a) |
| 2 | calcom/cal.com (now calcom/cal.diy) | MIT | d4efa0da8715756b8df4d49203a73cb92a0325f0 | 2021-05-30 | 47 : 3 | 3,560 | rejected: under 5,000 SLOC (rule b) |
| 3 | reactive-resume/reactive-resume | MIT | 4af318dc61bd2bde19aab7065b2c0a4b9166a642 | 2021-05-29 | 0 : 165 | 6,198 | rejected: no TypeScript at that date (rule a) |
| 4 | vercel/hyper | MIT | 21673ff978be0b600898c9640472c20334c064b0 | 2021-05-31 | 101 : 6 | 8,441 | **accepted** |
| 5 | appsmithorg/appsmith | Apache-2.0 | 9e8e432a1f9cc32c88d791d2317390cd2102581b | 2021-05-31 | 963 : 174 | 78,490 | **accepted** |
| 6 | ant-design/ant-design-pro | MIT | 7d9e9a2ddf6003a9d9aaa36cbb87c820a09bac7f | 2021-05-18 | 96 : 11 | 4,002 | rejected: under 5,000 SLOC (rule b) |
| 7 | wulkano/Kap | MIT | 45a7a522f1cdd547b8123b685ae7948a769cfb49 | 2021-05-11 | 125 : 74 | 11,220 | **accepted** |
| 8 | vercel/commerce | MIT | 1bc721de8313c15b837280a0a2e37c605af74560 | 2021-05-31 | 420 : 11 | 11,739 | **accepted** (fourth) |

Total SLOC of the four accepted: 109,890 (at least 40,000). Not walked, because the list was complete at four: fluent-reader, async-labs/saas, nodejs.org,
github-profile-readme-generator. Skipped as non-applications (libraries, frameworks, toolkits): ant-design, storybook, docusaurus, zustand, TanStack, trpc, payload, chakra, mantine
and similar; appwrite (a PHP backend). Two accepted repos are Electron apps with a React UI (hyper, Kap), one is a platform client (appsmith), one is a
Next.js application (commerce).

appsmith is 71% of the group's SLOC, so the pooled human share is mostly appsmith's. The per-repo table shows this and the report says so.

Human repos are cloned into a temp directory outside any repo with `git clone --filter=blob:none` and a checkout of the commit. No install, build, script or
git hook from them runs (`core.hooksPath=/dev/null`); scb-check only parses them. Only numbers and SHAs are committed.

## Agent group

Pooled, at the frozen rules, all under `--profile ts`:
- application A, at its head on the day of the run
- application B
- the sealed hold-out (hash-checked against a sealed manifest first; copied to a temp dir outside any repo)

Applications A and B are agent-written but also the calibration corpus, and the hold-out is spent for tuning; none were used to choose the rules after the freeze.

## Measures, per repo and per group

ast-only share = `ast_grep_flagged_loc / total_loc`; verbosity; `clone_loc / total_loc`; erosion; cog_erosion; SLOC (`total_loc`); ast-grep hits (count of `ts-` rule hits).
A group value is the pooled one: sums of numerators over sums of SLOC for the shares and verbosity (`verbosity_flagged_loc`, `clone_loc`, `ast_grep_flagged_loc`); erosion is
sum of `high_cc_mass` over sum of `total_mass`, cog_erosion is sum of `high_cog_mass` over sum of `total_cog_mass`, across the group's repos (`scripts/separation_score.py`).

## Pass rule

- **Pass on ast-only share:** the agent group's pooled ast-only share is greater than the human group's pooled ast-only share, **and** the two groups have at least 30 ast-grep hits between them.
- Under 30 hits across both groups: the result is "not enough hits to tell". That is not a pass.
- Verbosity and erosion get the same comparison (agent greater than human), reported as measured results with no pass rule.
- The outcome does not stop the stage and nothing is tuned afterwards. A non-pass goes in the report and, in plain words, at the top of the README's limits section.

## What was seen before this commit

- The size check printed only SLOC and skipped counts for the candidates, with one exception: while checking its language mix, a full unscored-by-rules report (`--disable-sg`: verbosity, erosion, cog_erosion, clone_loc, no ast-grep) was printed for hyper
  (verbosity 0.022, erosion 0.532, cog_erosion 0.737, clone_loc 186). Hyper was already accepted by the selection order at that point. No ast-grep (rule) score of any human repo has been seen.
- The frozen rules were scored on applications A and B during calibration, and on the hold-out once at the earlier 25-rule set (ast share 0.00061 against application A's 0.00106). Neither is a human-group score.
