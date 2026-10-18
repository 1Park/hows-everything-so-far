# qwen_stt_analysis.json

Original path: `evaluation/qwen_stt_analysis.json` · Original SHA-256: `604bac8d4c03982b1e4a8948769fe0fb6d290e3fc6a8b3363355e0c6e7f6cfde`

The original content is preserved in the code block below. See the [evaluation index](README.md) for how to restore it as an executable file. Line endings may have been normalized when it was stored as Markdown.

````json
{
  "totals": {
    "clean_correct": 18,
    "noisy_correct": 11,
    "clean_valid": 22,
    "noisy_valid": 18,
    "clean_false_refill": 2,
    "noisy_false_refill": 2,
    "same_valid_output": 14,
    "pairs": 24,
    "unique_source_cases": 18,
    "both_correct": 11,
    "degraded": 7,
    "improved": 0,
    "non_refill_pairs": 6,
    "request_errors": 0,
    "strict_exact": 0,
    "clean_median_s": 0.6472141000122065,
    "clean_p95_s": 1.0879163999925368,
    "noisy_median_s": 0.6436413499905029,
    "noisy_p95_s": 0.9423629000084475
  },
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.714734800014412,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6225540000014007,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6608438999974169,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6267931000038516,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6845605999988038,
      "noisy_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6439668999810237,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6560297999822069,
      "noisy_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6433157999999821,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 1.1840456000063568,
      "noisy_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 1.1099162999889813,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6192076999868732,
      "noisy_output": {
        "intent": "refill",
        "item": "rye",
        "portion": "normal"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6236809999973048,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6338925000163727,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6128541000070982,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6414444000110961,
      "noisy_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6175097999803256,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6145355000044219,
      "noisy_output": {
        "intent": "refill",
        "item": "rise",
        "portion": "small"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6103720999963116,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6344410000019707,
      "noisy_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6426498999935575,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6183260000252631,
      "noisy_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "small"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6982404999725986,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "bean_sprouts",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6585117999929935,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6929477999801748,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "clarify",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": false,
      "clean_correct": false,
      "clean_false_refill": false,
      "clean_latency_s": 0.6745247000071686,
      "noisy_output": {
        "intent": "clarify",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.647151200013468,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": false,
      "clean_false_refill": true,
      "clean_latency_s": 0.6529838000133168,
      "noisy_output": {
        "intent": "clarify",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6402181000157725,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "cancel",
        "item": null,
        "portion": null
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6134182000241708,
      "noisy_output": {
        "intent": "clarify",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.664502600004198,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "small"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6404495000024326,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.692931800003862,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": false,
      "clean_false_refill": false,
      "clean_latency_s": 0.667414399998961,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.752853399986634,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": false,
      "clean_false_refill": false,
      "clean_latency_s": 0.7571608000143897,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.7776955000008456,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6389170000038575,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6327610999869648,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": false,
      "clean_false_refill": true,
      "clean_latency_s": 0.6351944000052754,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": true,
      "noisy_latency_s": 0.609842399979243,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "double"
      },
      "clean_valid": false,
      "clean_correct": false,
      "clean_false_refill": false,
      "clean_latency_s": 0.6186135999741964,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "double"
      },
      "noisy_valid": false,
      "noisy_correct": false,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6469757999875583,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "cancel",
        "item": null,
        "portion": null
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.6030115000030492,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": false,
      "noisy_false_refill": true,
      "noisy_latency_s": 0.6796414999989793,
      "same_valid_output": false
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 0.7168755000166129,
      "noisy_output": {
        "intent": "refill",
        "item": "kimchi",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.9423629000084475,
      "same_valid_output": true
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
      },
      "clean_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      },
      "clean_valid": true,
      "clean_correct": true,
      "clean_false_refill": false,
      "clean_latency_s": 1.0879163999925368,
      "noisy_output": {
        "intent": "refill",
        "item": "rice",
        "portion": "normal"
      },
      "noisy_valid": true,
      "noisy_correct": true,
      "noisy_false_refill": false,
      "noisy_latency_s": 0.6346840000187512,
      "same_valid_output": true
    }
  ]
}
````
