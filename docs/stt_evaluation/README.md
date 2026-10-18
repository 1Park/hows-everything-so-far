# STT accuracy takes

`takes.json` holds every take recorded from /ui/stt.html: the sentence that was meant, what the backend returned, the word error rate, the take length and the backend that produced it.

The file is written by the board, so the numbers survive a reload and are the same for everyone who opens the page. Discarding a take on the page removes it here too.

`takes.json` itself is not tracked: the board rewrites it on every take, which blocked pulls. Export a run with **Copy as CSV** on the page, or copy the file off the board, and commit that deliberately when it is worth keeping.

## base.en vs tiny.en, 2026-10-18

`base-vs-tiny-20261018.json` holds the run behind the switch to `ggml-tiny.en`.
Each phrase was recorded once and transcribed by both servers, so a pair differs
only by model.

| | base.en | tiny.en |
| --- | --- | --- |
| exact match | 75% | 70% |
| mean WER | 10.4% | 15.0% |
| median transcribe | 6.9s | 3.0s |

Seventeen of twenty pairs were identical. tiny read one better, was looser on one
that kept its drink name, and lost one outright ("Coffee instead, please" became
"something is there please"). The drink name survived 19 of 20, and the operator
reviews the transcript before sending, so the remaining miss is recoverable while
a four-second wait on every request is not.

Both models also misheard "Just a half portion of water" as "I still have a
portion of water", which inverts the meaning. That one is not a model choice;
keep it out of the demo script.
