-- Formal meeting minutes (集团会议纪要) and meeting metadata
ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS meeting_location VARCHAR(255),
    ADD COLUMN IF NOT EXISTS host VARCHAR(100),
    ADD COLUMN IF NOT EXISTS recorder_unit VARCHAR(255);

ALTER TABLE summaries
    ADD COLUMN IF NOT EXISTS formal_minutes TEXT;
