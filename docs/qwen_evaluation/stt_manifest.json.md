# stt_manifest.json

원본 경로: `evaluation/stt_manifest.json` · 원본 SHA-256: `ba33fe25856c7b5e2c5435ff66ff7e43170785f01c9dc0e01f86eee6d5fa133c`

원본 내용을 아래 코드 블록에 보존했다. 실행 가능한 파일로 복원하는 방법은 [평가 인덱스](README.md)를 참조한다. 줄바꿈은 Markdown 저장 과정에서 정규화될 수 있다.

````json
{
  "description": "Synthetic phonetic text substitutions, not outputs of a measured STT engine. Expected labels retain original speaker intent. Some corruptions are ambiguous; abstention is not an unsafe action.",
  "prompt_sha256": "69c496f64c09bb84788ca7a67bb79664e6b583a139ea6d9216eca0891475520c",
  "temperature": 0,
  "pairs": [
    {
      "pair_id": "S01",
      "source_id": "simple_01",
      "clean": "Please refill the kimchi.",
      "noisy": "Please refill the kim chee.",
      "substitutions": "kimchi -> kim chee",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S02",
      "source_id": "simple_01",
      "clean": "Please refill the kimchi.",
      "noisy": "Please refill the kin chi.",
      "substitutions": "kimchi -> kin chi",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S03",
      "source_id": "simple_02",
      "clean": "Just a little bean sprouts, please.",
      "noisy": "Just a little been sprouts, please.",
      "substitutions": "bean -> been",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      }
    },
    {
      "pair_id": "S04",
      "source_id": "simple_02",
      "clean": "Just a little bean sprouts, please.",
      "noisy": "Just a little bean spouts, please.",
      "substitutions": "sprouts -> spouts",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      }
    },
    {
      "pair_id": "S05",
      "source_id": "simple_03",
      "clean": "More rice, please.",
      "noisy": "More rise, please.",
      "substitutions": "rice -> rise",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S06",
      "source_id": "simple_03",
      "clean": "More rice, please.",
      "noisy": "More rye, please.",
      "substitutions": "rice -> rye",
      "category": "ambiguous_menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S07",
      "source_id": "simple_04",
      "clean": "A small serving of kimchi, please.",
      "noisy": "A small serving of kim chee, please.",
      "substitutions": "kimchi -> kim chee",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "small"
      }
    },
    {
      "pair_id": "S08",
      "source_id": "simple_02",
      "clean": "Just a little bean sprouts, please.",
      "noisy": "Just a little been spouts, please.",
      "substitutions": "bean -> been; sprouts -> spouts",
      "category": "multiple",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      }
    },
    {
      "pair_id": "S09",
      "source_id": "english_01",
      "clean": "A small refill of rice, please.",
      "noisy": "A small refill of rise, please.",
      "substitutions": "rice -> rise",
      "category": "menu",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "small"
      }
    },
    {
      "pair_id": "S10",
      "source_id": "negation_01",
      "clean": "Not kimchi, just a little bean sprouts, please.",
      "noisy": "Not kim chee, just a little been sprouts, please.",
      "substitutions": "kimchi -> kim chee; bean -> been",
      "category": "multiple",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      }
    },
    {
      "pair_id": "S11",
      "source_id": "negation_03",
      "clean": "I'm good on bean sprouts. A little rice, please.",
      "noisy": "I'm good on been sprouts. A little rise, please.",
      "substitutions": "bean -> been; rice -> rise",
      "category": "multiple",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "small"
      }
    },
    {
      "pair_id": "S12",
      "source_id": "english_02",
      "clean": "Not kimchi. Bean sprouts please.",
      "noisy": "Knot kimchi. Bean sprouts please.",
      "substitutions": "Not -> Knot",
      "category": "negation",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S13",
      "source_id": "cancel_01",
      "clean": "No, I'm still eating.",
      "noisy": "Know, I'm still eating.",
      "substitutions": "No -> Know",
      "category": "negation",
      "current_request": {
        "item": "kimchi",
        "portion": "normal"
      },
      "expected": {
        "intent": "cancel",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S14",
      "source_id": "cancel_03",
      "clean": "Don't bring me kimchi.",
      "noisy": "Don't bring me kim chee.",
      "substitutions": "kimchi -> kim chee",
      "category": "refusal_menu",
      "current_request": {
        "item": "kimchi",
        "portion": "normal"
      },
      "expected": {
        "intent": "cancel",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S15",
      "source_id": "cancel_05",
      "clean": "I'd like to cancel the request I just made.",
      "noisy": "I'd like to council the request I just made.",
      "substitutions": "cancel -> council",
      "category": "cancel_word",
      "current_request": {
        "item": "kimchi",
        "portion": "normal"
      },
      "expected": {
        "intent": "cancel",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S16",
      "source_id": "edit_01",
      "clean": "No, just a small amount.",
      "noisy": "Know, just a small amount.",
      "substitutions": "No -> Know",
      "category": "negation",
      "current_request": {
        "item": "kimchi",
        "portion": "normal"
      },
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "small"
      }
    },
    {
      "pair_id": "S17",
      "source_id": "edit_02",
      "clean": "I'll change it to bean sprouts.",
      "noisy": "I'll change it to been sprouts.",
      "substitutions": "bean -> been",
      "category": "context",
      "current_request": {
        "item": "kimchi",
        "portion": "small"
      },
      "expected": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      }
    },
    {
      "pair_id": "S18",
      "source_id": "holdout_08",
      "clean": "Change it to rice, please.",
      "noisy": "Change it to rise, please.",
      "substitutions": "rice -> rise",
      "category": "context",
      "current_request": {
        "item": "kimchi",
        "portion": "small"
      },
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "small"
      }
    },
    {
      "pair_id": "S19",
      "source_id": "holdout_07",
      "clean": "Change it to a normal portion, please.",
      "noisy": "Change it to a normal potion, please.",
      "substitutions": "portion -> potion",
      "category": "portion",
      "current_request": {
        "item": "kimchi",
        "portion": "small"
      },
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S20",
      "source_id": "ambiguous_04",
      "clean": "Both kimchi and bean sprouts, please.",
      "noisy": "Both kim chee and been sprouts, please.",
      "substitutions": "kimchi -> kim chee; bean -> been",
      "category": "multiple",
      "current_request": null,
      "expected": {
        "intent": "clarify",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S21",
      "source_id": "ambiguous_06",
      "clean": "A double portion of kimchi, please.",
      "noisy": "A double portion of kim chee, please.",
      "substitutions": "kimchi -> kim chee",
      "category": "unsupported",
      "current_request": null,
      "expected": {
        "intent": "clarify",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S22",
      "source_id": "holdout_15",
      "clean": "Cancel my refill, please.",
      "noisy": "Council my refill, please.",
      "substitutions": "Cancel -> Council",
      "category": "cancel_word",
      "current_request": {
        "item": "kimchi",
        "portion": "normal"
      },
      "expected": {
        "intent": "cancel",
        "item": null,
        "portion": null
      }
    },
    {
      "pair_id": "S23",
      "source_id": "simple_01",
      "clean": "Please refill the kimchi.",
      "noisy": "Please re fill the kimchi.",
      "substitutions": "refill -> re fill",
      "category": "segmentation",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      }
    },
    {
      "pair_id": "S24",
      "source_id": "simple_03",
      "clean": "More rice, please.",
      "noisy": "More rice, pleas.",
      "substitutions": "please -> pleas",
      "category": "noncritical",
      "current_request": null,
      "expected": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      }
    }
  ]
}
````
