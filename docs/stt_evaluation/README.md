# STT accuracy takes

`takes.json` holds every take recorded from /ui/stt.html: the sentence that was meant, what the backend returned, the word error rate, the take length and the backend that produced it.

The file is written by the board, so the numbers survive a reload and are the same for everyone who opens the page. Discarding a take on the page removes it here too.

`takes.json` itself is not tracked: the board rewrites it on every take, which blocked pulls. Export a run with **Copy as CSV** on the page, or copy the file off the board, and commit that deliberately when it is worth keeping.
