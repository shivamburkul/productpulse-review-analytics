SAMPLE CSV FILES  (upload any of them on the first page)

1_sentiment_test_synthetic.csv   52 rows, SYNTHETIC. Clear positive, negative, neutral, mixed and negated sentences with an
                                 expected_sentiment column (used by the tests to measure accuracy).
2_multi_product_synthetic.csv    600 rows, SYNTHETIC. 6 products x several features, for product comparison and feature analysis. Has a rating column.
3_dated_reviews_synthetic.csv    1,260 rows, SYNTHETIC. 3 products, 12 months of 2025 with a review_date column, for real date-based trends.
                                 (NovaPhone 9 battery reviews get worse from July on - built in on purpose.)
4_real_amazon_reviews_full.csv   7,905 REAL review sentences, 14 products. No dates. human_label = sentiment given by human annotators (ignored by the app).
5_real_amazon_cameras.csv        1,440 rows, real, four cameras only (quick demo).
schema_example.csv               The smallest valid file, showing optional columns.

Required columns: product (or product_name) and review text (review, comment, text or review_text).
Optional: rating, review_date / date, review_id.

SOURCE OF THE REAL DATA (files 4 and 5)
Hu, M. and Liu, B. (2004). "Mining and Summarizing Customer Reviews", KDD-2004. Customer review datasets (Amazon reviews):
https://www.cs.uic.edu/~liub/FBS/sentiment-analysis.html . Obtained from the NLTK corpora product_reviews_1 and product_reviews_2.
The authors make the data available for research use; it is included here for this educational project. Check the source page before any other use.
Each row is one sentence of a review, so the rows are short, comment-like texts.
