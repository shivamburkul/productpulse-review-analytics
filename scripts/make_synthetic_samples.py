import csv
import os
import random

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_csv")
random.seed(7)

CLEAR = {
    "positive": ["The camera quality is excellent.", "I love this phone, it works perfectly.", "Great screen, very bright and sharp.", "The battery lasts all day, I am very happy.",
                 "Fantastic value for the price.", "Setup was easy and the software is smooth.", "The sound is amazing and the build feels solid.", "Best purchase I have made this year.",
                 "Very fast and reliable, highly recommended.", "The design is beautiful and comfortable to hold.", "Excellent performance, no lag at all.", "Wonderful speakers with deep bass."],
    "negative": ["The battery drains very quickly.", "Terrible camera, the photos are blurry.", "The screen cracked within a week, awful quality.", "Worst purchase ever, total waste of money.",
                 "The software keeps crashing and freezing.", "Way too expensive for what it offers.", "The charger stopped working after two days.", "Very slow and laggy, I regret buying it.",
                 "The plastic feels cheap and flimsy.", "Poor sound, the volume is far too low.", "Disappointing display, the colors look washed out.", "It broke after a month and support was useless."],
    "neutral": ["The display is okay.", "I have used this product for three days.", "It arrived on Tuesday in a brown box.", "The phone comes in black and silver.",
                "The package includes a charger and a manual.", "I bought this for my sister.", "The screen is average, nothing special.", "It has a six inch display.", "The box was medium sized.", "I use it mostly at home."],
    "mixed": ["The camera is excellent, but the battery is terrible.", "Great screen but the software crashes a lot.", "The sound is amazing, however the build feels flimsy.",
              "Love the design, but it is far too expensive.", "Fast performance although the battery drains quickly.", "The display is gorgeous, but the camera is disappointing.",
              "Excellent speakers but terrible software.", "The price is great, but the quality is awful.", "Very easy setup, but the screen is dim and poor.", "Battery life is wonderful but the camera is bad."],
    "negated": ["The phone is not good.", "The software is not bad.", "The camera is not great at all.", "I am not happy with the battery.", "The screen is not terrible.", "This is not a bad deal.",
                "The speakers are not impressive.", "The build quality is not poor."],
}
EXPECT_NEG = {"The phone is not good.": "negative", "The software is not bad.": "positive", "The camera is not great at all.": "negative", "I am not happy with the battery.": "negative",
              "The screen is not terrible.": "positive", "This is not a bad deal.": "positive", "The speakers are not impressive.": "negative", "The build quality is not poor.": "positive"}
RATING = {"positive": 5, "negative": 1, "neutral": 3, "mixed": 3}


def write(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(name, len(rows))


rows, n = [], 0
for kind, texts in CLEAR.items():
    for t in texts:
        n += 1
        exp = EXPECT_NEG.get(t, kind) if kind == "negated" else kind
        rows.append(["T%03d" % n, "TestPhone A" if n % 2 else "TestPhone B", t, exp, RATING.get(exp, 3)])
write("1_sentiment_test_synthetic.csv", ["review_id", "product", "review_text", "expected_sentiment", "rating"], rows)

PRODUCTS = {  # product -> {feature: positive probability}
    "AuroraPhone X": {"Camera": .85, "Battery": .3, "Display": .8, "Performance": .7, "Price": .35},
    "BoltPhone Lite": {"Camera": .4, "Battery": .85, "Display": .45, "Performance": .5, "Price": .9},
    "ClearView Monitor": {"Display": .92, "Design": .7, "Price": .4, "Build Quality": .75, "Software": .5},
    "EchoBuds Pro": {"Audio": .88, "Battery": .6, "Design": .7, "Build Quality": .4, "Software": .3},
    "FitBand 5": {"Battery": .8, "Display": .5, "Software": .35, "Design": .75, "Price": .8},
    "GigaBook 14": {"Performance": .88, "Display": .7, "Battery": .55, "Build Quality": .6, "Price": .3},
}
POS = {"Camera": ["The camera takes sharp, vivid photos.", "Photos look great, even in low light.", "Love the camera and the zoom."],
       "Battery": ["The battery easily lasts two days.", "Great battery life, charging is fast.", "Battery performance is wonderful."],
       "Display": ["The display is bright and beautiful.", "Colors on the screen look stunning.", "Excellent screen, very sharp."],
       "Performance": ["It runs fast with no lag.", "Performance is excellent and very smooth.", "Apps open quickly, very reliable."],
       "Price": ["Great value for the money.", "The price is very fair for what you get.", "Cheap but excellent quality."],
       "Design": ["The design is sleek and comfortable.", "Beautiful, light and compact design.", "I love the look and feel."],
       "Build Quality": ["The build is solid and durable.", "Feels sturdy with a premium metal body.", "Excellent build quality."],
       "Software": ["The software is easy to use and smooth.", "Setup was simple and the interface is clean.", "Updates are quick and the menu is intuitive."],
       "Audio": ["The sound is crisp with deep bass.", "Amazing audio and clear volume.", "Music sounds fantastic on these."]}
NEG = {"Camera": ["The camera is disappointing, photos are blurry.", "Terrible camera in low light.", "Camera quality is poor."],
       "Battery": ["The battery drains very quickly.", "Terrible battery life, charging is slow.", "Battery died after a few hours."],
       "Display": ["The screen is dim and washed out.", "Disappointing display with poor colors.", "The display flickers, awful."],
       "Performance": ["It is slow and laggy.", "Performance is bad, the apps freeze.", "Constant crashes, very sluggish."],
       "Price": ["Way too expensive for what it offers.", "Overpriced, not worth the money.", "The price is far too high."],
       "Design": ["The design is ugly and bulky.", "Awkward shape and uncomfortable to hold.", "Heavy and clumsy design."],
       "Build Quality": ["The plastic feels cheap and flimsy.", "It broke after a month.", "Poor build quality, started cracking."],
       "Software": ["The software is buggy and confusing.", "Setup was difficult and the app keeps crashing.", "Terrible interface, updates break things."],
       "Audio": ["The sound is tinny with weak bass.", "Poor audio, the volume is too low.", "Disappointing sound quality."]}
rows, n = [], 0
for prod, feats in PRODUCTS.items():
    for _ in range(100):
        n += 1
        f = random.choice(list(feats))
        ispos = random.random() < feats[f]
        text = random.choice((POS if ispos else NEG)[f])
        if random.random() < .25:
            g = random.choice([x for x in feats if x != f])
            gp = random.random() < feats[g]
            text += " " + random.choice((POS if gp else NEG)[g])
        rows.append(["M%04d" % n, prod, text, random.choice([4, 5]) if ispos else random.choice([1, 2])])
write("2_multi_product_synthetic.csv", ["review_id", "product", "review_text", "rating"], rows)

rows, n = [], 0
for prod, base in (("NovaPhone 9", .75), ("TerraPad Mini", .6), ("PulseWatch S", .7)):
    for month in range(1, 13):
        for _ in range(35):
            n += 1
            drop = prod == "NovaPhone 9" and month >= 7
            feat = random.choice(["Battery", "Camera", "Display", "Performance", "Software"])
            p = base - (.5 if (drop and feat == "Battery") else 0) + (.01 * month if prod == "TerraPad Mini" else 0)
            ispos = random.random() < p
            text = random.choice((POS if ispos else NEG)[feat])
            rows.append(["D%04d" % n, prod, text, "2025-%02d-%02d" % (month, random.randint(1, 28))])
write("3_dated_reviews_synthetic.csv", ["review_id", "product", "review_text", "review_date"], rows)

write("schema_example.csv", ["review_id", "product", "review_text", "rating", "review_date"],
      [["1", "Example Phone", "The battery lasts all day and the screen is bright.", "5", "2025-01-15"], ["2", "Example Phone", "Camera is poor in low light.", "2", "2025-01-20"]])
