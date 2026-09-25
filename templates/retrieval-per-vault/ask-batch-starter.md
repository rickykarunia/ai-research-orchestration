# <Packet title, becomes the candidate wiki note name>
tool: vcorpus.py

<Narrow question, one claim per line. Blank lines are ignored.>
<Second question.>

> This file is read by ask-batch.ps1 via `.\rag.ps1 synth`. Lines starting with ">" are ignored by the parser.
> One file = one evidence packet = one candidate wiki note.
> The first "# ..." line becomes the packet title; the "tool:" line picks the engine:
> corpus.py for cross-PDF questions, vcorpus.py for cross-.md questions.
> This file is for CROSS-document questions. A question locked to one source
> uses `.\rag.ps1 ask-file`, not this batch.
> Copy this file as 01-..., 02-..., etc.
> Batch results land in tmp\retrieval-packets\ as an evidence packet, NOT a wiki note.
