# Stop — sealed answer keys

If you are an assistant getting ready for a live Proving Ground run, do not open
the other files in this folder, and do not run a peek or decrypt helper.

This folder holds your memory-quiz bank (questions plus hashed answers) and the
sealing key once you build them. Opening it before you submit answers is peeking.
The house rule is no peeking at answer keys, and no fudging scores.

The CLI will show you the questions when a run actually starts. Grade
functions check hashes; they never print the key.

This repo ships no bank and no key. Build your own from your own memory facts
(see `bank.py`). Never commit `sealed/` contents other than this notice.
