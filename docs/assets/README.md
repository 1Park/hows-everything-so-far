# Architecture illustration

`cups-example.jpg`는 `docs/architecture.html`에서 사용하는 AI 생성 설명용 이미지다. 실제 카메라 입력·평가 데이터·모델 실행 결과가 아니다. HTML의 bbox·종류·잔량·confidence도 설명을 위한 예시다.

실제 앱의 기본 fixture 화면과 이미지/영상 transport 테스트도 같은 사진을 사용한다. fixture 점수·잔량·bbox는 수동 값이며 Vision 정확도 검증 자료가 아니다.

생성: 2026-10-16, 내장 `image_gen` 도구. 원본 PNG를 JPEG로 변환해 저장했다. 사진의 생성 프롬프트는 아래와 같다.

```text
Use case: photorealistic-natural. Asset type: example camera frame for a technical architecture explainer, not actual test data. Create one landscape photograph of a light oak restaurant tabletop, shot from a slightly elevated front angle. Exactly three separate identical plain clear cylindrical drinking glasses, evenly spaced left center right, all completely visible and not overlapping, with generous space between. Left glass has only a small amount of clear water at the bottom (roughly 15 percent full); center glass has dark brown fizzy cola about 75 percent full; right glass has black coffee about 50 percent full. No ice, no straws, no handles. Neutral warm cafe background out of focus, natural light, realistic glass reflections and clearly visible liquid levels. Align glass bases along same horizontal line. Leave margin around glasses for bounding box overlays. No people, no hands, no text, no labels, no graphics, no logos, no watermarks. Landscape 3:2 composition.
```
