# ONE-HOUR DEMO SPRINT (instructions from the user, saved verbatim)

ONE-HOUR DEMO SPRINT. I must present a working Computer Vision web app TONIGHT. Time-box: about 60 minutes.
Reuse everything already built (Phases 1-3 code, templates, auto-proposed regions, EasyOCR setup, backend tests).
Follow CLAUDE.md honesty rules: no fake data, no hard-coded results, nothing invented. Every image, box,
number and chart shown in the UI must come from the backend, uploaded files or the database.
Do not use GSD. Do NOT run long self-tests or training. Write several files per tool call. Commit after each
numbered step. Keep the app runnable after every step. Skip: Template Studio, HTR training, YOLO training,
evaluation pages, long docs.

STEP 1 (about 5 min): Quick close of Phase 3. Run the template-identification self-test on a SMALL sample
(3 pages per distortion level), save results to reports/, merge to main. Preload the EasyOCR English + Nepali
models at backend startup so the first upload is not slow.

STEP 2 (about 8 min): Demo form generator. For nicasia, laxmisunrise and machhapuchhre, create 2 filled
fictional forms each, all pages, using the auto-proposed P1 regions: Nepali and English values, handwriting-style
fonts (Kalam and any other open fonts available), blue/black/faded ink shades, hand-drawn ticks in checkboxes,
then phone-photo distortion (perspective, rotation, shadow, blur, noise, JPEG). Also make one extra strongly
rotated + shadowed photo of one form. Save ground_truth.json separately and never use it during processing.
Label every file SYNTHETIC. No real people, no real photos.

STEP 3 (about 15 min): REAL COMPUTER VISION PIPELINE in the backend. Every stage saves a real intermediate
image and its parameters, timing and metrics:
 original -> quality metrics (Laplacian blur, resolution, skew angle, glare) -> grayscale -> denoise ->
 CLAHE (+ before/after histogram data) -> adaptive threshold -> Canny edges -> contours with the detected
 document quadrilateral -> perspective-corrected page -> deskewed page -> ORB/SIFT keypoints -> feature matches
 against every enrolled template page with RANSAC inliers -> template + page identification with confidence ->
 homography alignment overlay -> template region boxes mapped onto the page -> OpenCV rectangle/line detection
 on the aligned page used to snap each template box to the real printed box (record the before/after shift and
 IoU) -> field crops -> checkbox squares found by contours with ink-fill ratio -> EasyOCR (English + Nepali) with
 confidence -> normalise + validate -> structured record with status (auto_accepted / needs_review /
 unreadable / empty).
 Run as a background job with real per-stage progress and timings. Expose each stage's image and parameters
 through the API, and allow re-running a stage with changed parameters (CLAHE clip limit, denoise strength,
 threshold method, matcher type) so the UI can update it live.
 Keep the field-detection step behind the existing detection interface. The system status must say honestly:
 "Template-alignment mode with OpenCV box snapping. YOLO model not trained yet." Never label anything a YOLO
 result.

STEP 4 (about 7 min): API, all typed and tested quickly: login (JWT), upload (images/PDF, validation), process,
job progress (SSE or polling), documents list (server-side pagination/sort/filter), document detail, stages,
crops, patch field, verify field, search, export JSON/CSV, dashboard stats from the DB (zeros when empty),
system status. Add a script to create the admin user with a password I type in (nothing stored in code).

STEP 5 (about 20 min): FRONTEND, the showpiece. React + Vite + TypeScript + Tailwind + shadcn/ui +
framer-motion + Recharts + lucide-react + TanStack Query. Fonts: Inter and Noto Sans Devanagari. Dark theme by
default with a light toggle: deep neutral background, one bright accent colour, subtle glass cards, soft glow
on active elements, smooth transitions, skeleton loaders, polished empty and error states. Responsive at
1920/1440/1024/768/390 px, no horizontal overflow, touch targets at least 44 px. Animations may only reveal REAL
results: boxes appearing one by one, match lines drawing between page and template, a scan line sweeping the page
while the job really runs, numbers counting up to values from the database. Never fake progress or data.

 a) App shell: sidebar (bottom nav on mobile), top bar with system status chip (mode, OCR engine, DB, job
    tray with live progress).
 b) Dashboard: real KPI cards, activity chart, status breakdown, recent documents, per-template counts,
    average field confidence, all from the DB.
 c) Upload: big drag-and-drop, mobile camera capture, reorderable page thumbnails, quality warnings
    (blur/skew/glare from the backend), then a LIVE stepper using the real stage names and timings.
 d) VISION LAB (the main CV showpiece): a horizontal stage timeline; click a stage to see its real image large;
    before/after slider between consecutive stages; parameter sliders that re-run that stage live; CLAHE
    histogram chart; contour view showing the document quadrilateral; keypoint-match view with lines and the
    inlier count; homography overlay with a blend slider; box-snapping view (template box vs snapped box);
    crop gallery with each crop's OCR text, confidence and checkbox ink ratio; stage-timing bar chart; a short
    "why this step exists" tooltip per stage for my viva.
 e) Review page: zoomable, pannable page image with clickable boxes coloured by confidence; selecting a box
    highlights its field and vice versa; field crop, raw OCR vs normalised value, confidence bar, editable
    value, Verify button; low-confidence fields highlighted; nothing auto-verified; on mobile the inspector is a
    bottom sheet.
 f) Documents list, Search (server-side, filters, pagination, empty/loading/error states), Export buttons,
    document detail with processing timeline.
 g) A visible mode banner showing exactly what is real.

STEP 6 (about 5 min): One command to start backend + frontend (scripts/dev.py or npm script). Then TEST FOR
REAL once: start both, upload one generated form per bank plus the rotated/shadowed one; confirm every Vision
Lab stage shows a real image, fields save, search and export work. Take screenshots of Vision Lab and Review at
1440 px and 390 px, LOOK at them, and fix overflow, broken images and ugly layouts. One fix pass only.

STEP 7 (about 3 min): Short README with exact Windows PowerShell commands to start the app and log in.
Update PROGRESS.md with what works, what was skipped and the honest limitations.

If time or usage runs low, finish the steps in order and make sure everything that exists RUNS and looks good.
Put the most effort into the Vision Lab and the Review page. When done, stop and tell me:
(a) the exact commands to start the app, (b) how to log in, (c) which demo form files to upload,
(d) what works, (e) what is not done.
