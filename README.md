# ProductPulse

### Product Review Analytics and Data Integrity Platform

ProductPulse is a web application that helps users understand customer feedback through product review analysis. It analyses sentiment, identifies commonly discussed product features, compares products, displays trends, and generates reports. It also includes a dataset integrity feature to detect changes made to registered review data.

## Features

- **Review Upload and Validation:** Upload CSV files and view information about accepted and rejected rows.
- **Sentiment Analysis:** Classifies reviews as positive, negative, neutral, or mixed and calculates sentiment scores.
- **Analytics Dashboard:** Displays review statistics, sentiment distribution, product rankings, keywords, and charts.
- **Product Insights:** Explore individual products and understand their strengths and common complaints.
- **Product Comparison:** Compare two products using their review analysis results.
- **Feature-Level Analysis:** Identify commonly discussed product features and their associated sentiment.
- **Review Analyzer:** Search and inspect individual reviews, cleaned text, sentiment scores, keywords, and detected features.
- **Trend Analysis:** Explore review and sentiment patterns using available dates or clearly identified groups based on file order.
- **Dataset Integrity Verification:** Register and verify dataset fingerprints using SHA-256 hashing, a Merkle tree, and a local hash-linked ledger.
- **Report Generation:** Export product reports in CSV, JSON, and PDF formats.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Web Framework | Flask |
| Data Processing | Apache Spark (PySpark) |
| Sentiment Analysis | VADER Sentiment |
| Frontend | HTML, CSS, JavaScript |
| Charts | Chart.js |
| Data Integrity | SHA-256, Merkle Tree, Local Hash-Linked Ledger |
| PDF Reports | ReportLab |

## Requirements

Before running the application, ensure that you have:

- Python installed
- Java Development Kit (JDK) installed and available on your system PATH
- Visual Studio Code or another suitable code editor
- The dependencies listed in `requirements.txt`

Check Python and Java from the terminal:

```powershell
python --version
java -version
```

## Installation and Setup

### 1. Clone the Repository

```powershell
git clone https://github.com/YOUR-USERNAME/productpulse-review-analytics.git
cd productpulse-review-analytics
```

Replace `YOUR-USERNAME` with your GitHub username.

If you have already downloaded the project, open its folder in Visual Studio Code and run the commands below from the folder containing `app.py`.

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
```

### 3. Install Dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Run the Application

```powershell
.\.venv\Scripts\python.exe app.py
```

Once the server starts, open the following address in your browser:

```text
http://127.0.0.1:5000
```

Keep the terminal open while using the application. Press `Ctrl+C` in the terminal to stop the server.

## Input Dataset

The application accepts CSV files containing product names and customer reviews. Ratings, dates, and review identifiers can also be provided when available.

Recommended column names:

| Column | Description |
|---|---|
| `product` | Product name or identifier |
| `review_text` | Customer review text |
| `rating` | Optional product rating |
| `date` | Optional review date |
| `review_id` | Optional review identifier |

Example CSV data:

```csv
review_id,product,review_text,rating,date
R001,Example Phone,"The camera is clear and the battery lasts all day.",5,2026-01-10
R002,Example Phone,"The battery drains quickly.",2,2026-01-12
```

Sample datasets are available in the `sample_csv/` directory and can be used to explore the application's features.

## How to Use

1. Open ProductPulse in your browser.
2. Upload a sample or compatible CSV dataset.
3. Wait for the review-processing stages to complete.
4. Explore the dashboard and sentiment distribution.
5. Open Product Insights to analyze or compare products.
6. Use Review Analyzer to search and examine individual reviews.
7. Explore Trends to understand review patterns.
8. Use Dataset Integrity to register and verify a dataset.
9. Export the available analysis results as CSV, JSON, or PDF reports.

## Dataset Integrity Verification

ProductPulse includes a local dataset-integrity mechanism designed to detect changes to registered review data.

The mechanism uses:

- **SHA-256 hashing** to generate fingerprints for review data.
- **Merkle trees** to combine row fingerprints into a dataset-level fingerprint.
- **A hash-linked ledger** to record dataset fingerprints and help detect changes.

This feature identifies differences between the registered data and the data being checked. It does not establish whether a review is genuine or identify the person responsible for a change.

## Project Structure

```text
productpulse-review-analytics/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── backend/
│   ├── chain.py
│   ├── datasets.py
│   ├── nlp_engine.py
│   ├── report.py
│   ├── spark_job.py
│   └── spark_compat.py
│
├── frontend/
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       ├── app.js
│       └── chart.umd.js
│
├── sample_csv/
│
└── data/
    ├── uploads/
    ├── datasets/
    ├── logs/
    └── ledger.json
```

The `data/` directory contains runtime-generated files. Its exact contents may vary depending on application usage.

## Limitations

- Sentiment analysis can misinterpret sarcasm, ambiguous wording, or context.
- Product-feature detection relies on configured keyword rules.
- Results are analytical estimates and should not be treated as ground truth.
- Trend analysis depends on the availability and quality of date information.
- Dataset integrity verification detects data changes but does not prove review authenticity.
- The integrity ledger operates locally and is not a public blockchain network.

## Future Improvements

- Improve feature detection for a wider range of product categories.
- Enhance sentiment analysis for context and complex language.
- Add support for more dataset formats.
- Introduce additional comparison and visualization options.
- Improve scalability and report customization.

## Repository Information

**Project Title:** ProductPulse: Product Review Analytics and Data Integrity Platform

**Recommended Repository Name:** `productpulse-review-analytics`

**Category:** Web Application, Review Analytics, Data Processing, and Data Integrity