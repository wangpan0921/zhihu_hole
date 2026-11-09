---
name: generate-kid-coding-video
description: Generate Minecraft-style narrated lesson videos from kid-coding Markdown articles with sentence-broken narration.txt captions, final-screen-order slide alignment, and an automatically extracted quiz.txt question and answer from the “一起改改看” section. Use when Codex needs to prepare, validate, render, or troubleshoot a 少儿编程课程讲解视频, narration subtitles, subtitle-to-picture mismatches, interactive quiz screens, horizontal MP4, or vertical MP4 with scripts/kid_coding_video.py.
---

# Generate Kid Coding Video

Use the project script as the single implementation:

```bash
python scripts/kid_coding_video.py --project-root <course-project> --lesson <number> <mode>
```

Prefer the target project's virtual-environment Python when it provides `imageio`, `numpy`, `Pillow`, `edge-tts`, and FFmpeg support.

Keep these invariants throughout the workflow:

- Treat `narration.txt` as the source for both speech and bottom captions.
- Validate against the final slide sequence after Quiz insertion, not only the article's original pagination.
- Require each slide's visible body, speech, and caption to describe the same step. Similar section titles are not sufficient evidence of alignment.
- Stop before TTS or rendering when any screen is structurally or semantically mismatched.

## Prepare Text

1. Locate the course project containing `kid_coding/` and the lesson Markdown.
2. Inspect the article's `## 一起改改看` section. Require a question marked `先预测` and an answer marked `揭晓`; improve the article first if either is missing.
3. Generate text artifacts without rendering:

```bash
<course-project>/venv/bin/python scripts/kid_coding_video.py \
  --project-root <course-project> --lesson <number> --prepare-only
```

4. Inspect the lesson folder's `narration.txt` and `quiz.txt`.

Treat `narration.txt` as the only source for both speech and captions. Preserve every `### number | slide title` line and its order. Treat each non-empty body line as one timed caption screen. The generator breaks fresh narration at sentence or clause boundaries and limits generated lines to 34 characters; keep manual edits similarly concise.

Preserve an existing valid `quiz.txt`. When it is absent or contains only comments, the script generates one complete multiple-choice question from `一起改改看`: the `先预测` text becomes the question, the first `揭晓` result becomes option A and the answer, and the reveal content becomes the explanation. Verify that `after`, `question`, at least three options, `answer`, `explain`, and `pause` are all present and faithful to the article.

## Validate Alignment

Run the structural and content comparison before rendering:

```bash
<course-project>/venv/bin/python scripts/kid_coding_video.py \
  --project-root <course-project> --lesson <number> --check-narration
```

Treat this command as a required pre-render gate. Read its screens in the reported final order, including generated `quiz_q` and `quiz_a` screens. Compare every displayed slide with its narration semantically, not merely by title or shared keywords.

At every Quiz insertion, explicitly verify this local sequence:

1. The prediction/content screen asks the learner to predict.
2. The Quiz question screen contains the complete question and options.
3. The Quiz answer screen owns the reveal, output, and explanation.
4. The first following content screen shows and narrates the hands-on modification task.
5. The second following content screen shows and narrates the next-step or error experiment.

Inspect at least the screen before the Quiz, both Quiz screens, and the next two content screens. Watch for the common failure where Quiz insertion shifts narration numbers while the article's original reveal pages remain in place. Do not accept a sequence where the picture still reveals an answer but the narration has already moved on to an exercise.

Choose the fix based on the mismatch:

- Fix wording or line breaks in `narration.txt` only when the visible screen is correct and the narration is stale or poorly segmented. Preserve block headings.
- Fix slide construction or Quiz follow-up mapping in `scripts/kid_coding_video.py` when the visible screen contains the wrong article blocks. Do not hide a picture-order bug by rewriting narration to describe the wrong screen.
- Remove duplicate article reveal pages from the post-Quiz flow when the generated Quiz answer screen already presents that reveal, while preserving the actual follow-up tasks.

Run `--check-narration` again after every alignment change. If an article edit rebuilds the file, inspect `narration.txt.bak`, reapply only still-relevant manual phrasing, and repeat the full final-order check.

## Render And Verify

Render the horizontal video after text validation:

```bash
<course-project>/venv/bin/python scripts/kid_coding_video.py \
  --project-root <course-project> --lesson <number>
```

Add `--vertical` only when a 9:16 output is requested.

Confirm that the final MP4 exists, has an audio stream, and has nonzero duration. Spot-check caption transitions around long sentences and every Quiz insertion. Confirm the prediction screen is followed by the Quiz question, countdown, Quiz answer/explanation, and the correct follow-up tasks. Report the output paths and any manual edits made to `narration.txt` or `quiz.txt`.

Do not use render success alone as proof of alignment. After muxing:

1. Fully decode the MP4 to catch corrupt video or audio streams.
2. Extract frames or a contact sheet around every Quiz insertion.
3. Visually compare the bottom caption with the visible body on the Quiz question, Quiz answer, and next two content screens.
4. Confirm the corrected MP4 is the requested output path and was regenerated after the latest text or mapping change.

If any sampled screen is mismatched, fix the source mapping, rerun `--check-narration`, regenerate TTS and video, and repeat the visual check. Report completion only after the final MP4 passes both structural checking and visual spot-checking. Include the final screen order around the Quiz in the handoff so the user can verify the exact correction.
