1. **Train & Save a Model** — Train a basic ML classifier and save it to disk; your first reusable model artifact.

2. **Simple Model Registry** — Track model versions, their metrics, and which one is currently "live" in a database or file.

3. **Batch Prediction Pipeline** — Load the registered model and run it on new data on a schedule, saving the predictions.

4. **Prediction Logging System** — Log every input and prediction to a file/database, building a history to analyze later.

5. **Data Drift Detector** — Compare today's input data distribution to the training data using statistical tests and output a drift score.

6. **Concept Drift Detector** — Compare model accuracy over time against real outcomes to catch performance decay, not just input changes.

7. **Alerting System** — Send a notification (console, email, or Slack webhook) when the drift score crosses a set threshold.

8. **Monitoring Dashboard** — A simple Streamlit dashboard showing live accuracy, drift scores, and alert history over time.

9. **Automated Retraining Trigger** — Automatically kick off a retraining script on fresh data when drift is detected.

10. **Safe Deployment (Shadow/Canary)** — Deploy a new model version alongside the old one and compare their outputs before fully switching over.

11. **Production MLOps Platform with Drift Detection** — Combine all of the above into one system: registry + deployment + logging + drift detection + alerting + auto-retraining.