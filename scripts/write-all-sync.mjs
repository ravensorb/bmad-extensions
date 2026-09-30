// One buffered, complete write to a raw fd, for gate scripts that print findings and exit.
//
// THE BUG THIS EXISTS FOR. `console.log`/`console.error` are ASYNCHRONOUS when the stream is a
// PIPE -- which is exactly how CI and every one of this repo's own test suites run these
// scripts. Bytes still queued when `process.exit()` tears the process down are DISCARDED, with
// no error anywhere. `check-docs.mjs` shipped that for its whole life: a correct
// "231 documentation problem(s)" header over 142 delivered findings and no closing advice, in
// 10 of 20 runs. The same command through a shell pipeline was intact 8/8, so it only ever
// truncated where a human was not reading it.
//
// WHAT ACTUALLY TRIGGERS IT -- measured on this tree, and not what it looks like. It is the
// number of QUEUED WRITES, not the payload size. A single `process.stderr.write` of 128 KB was
// intact 20/20; a loop of `console.error` truncates as the line count climbs:
//
//     100 lines   9.7 KB    0/20
//     300 lines  29.0 KB    2/20   worst delivered 57%
//     660 lines  63.8 KB    2/20   worst delivered 73%
//    1000 lines  96.7 KB    6/20   worst delivered 18%
//    2000 lines 193.4 KB   14/20   worst delivered  9%
//    5000 lines 483.4 KB   20/20   worst delivered  3%
//
// So the onset is around 300 lines and it is PROBABILISTIC the whole way up -- which is the
// property that matters, because it means a gate can be wrong intermittently in CI and right
// every time you run it by hand. One `writeAllSync` call is one write, and is therefore safe at
// any size the table above covers.
//
// TWO RULES FOLLOW, and both are load-bearing:
//   1. Assemble the whole report as ONE string and write it through here.
//   2. Set `process.exitCode` and fall through -- NEVER `process.exit()`.
// Doing only (1) still truncates: a lone buffered write races the teardown just as the loop
// does. Doing only (2) is correct but leaves the report at the mercy of the event loop.
//
// `fs.writeSync` alone is not sufficient either: on a non-blocking fd it can write fewer bytes
// than asked, or throw EAGAIN, and either one truncates exactly as silently as the race it
// replaces. Hence the loop and the retry.
//
// This lives in its own module rather than in `check-docs.mjs` because four gate scripts need
// it and importing a checker to borrow a utility would run that checker's module scope.
import fs from "node:fs";

export function writeAllSync(fd, text) {
  const buf = Buffer.from(text, "utf8");
  let off = 0;
  while (off < buf.length) {
    try {
      off += fs.writeSync(fd, buf, off, buf.length - off);
    } catch (err) {
      if (err.code === "EAGAIN") continue;
      throw err;
    }
  }
}
