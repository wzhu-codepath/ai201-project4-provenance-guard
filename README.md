# Provenance Guard

A small Flask API for text provenance checking.

## Endpoints

- `POST /submit`: classifies submitted text and writes the result to the audit log.
- `POST /appeal`: marks the content as under review, logs the appeal with the original decision, and returns a confirmation.

## Rate Limit

`POST /submit` is limited to `5 per minute` and `30 per hour` per `creator_id` when available, otherwise per client IP.

These limits are meant for normal writer behavior while blocking abuse: the minute window allows a short burst of edits, and the hourly window prevents script flooding over time.