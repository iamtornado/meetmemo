export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  role: "admin" | "editor" | "member";
  auth_provider: string;
  is_active: boolean;
  created_at: string;
}

export interface Team {
  id: string;
  name: string;
  description: string | null;
  created_by: string;
  created_at: string;
  members: TeamMember[];
}

export interface TeamMember {
  user_id: string;
  email: string;
  display_name: string;
  role: "owner" | "editor" | "viewer";
  joined_at: string;
}

export interface Meeting {
  id: string;
  title: string | null;
  date: string | null;
  duration_seconds: number | null;
  status: "uploading" | "uploaded" | "processing" | "completed" | "failed" | "cancelled";
  team_id: string | null;
  created_by: string;
  audio_path: string;
  file_format: string;
  file_size: number;
  error_message: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  meeting_location: string | null;
  host: string | null;
  recorder_unit: string | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingListResponse {
  items: Meeting[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TranscriptSegment {
  id: number;
  seq_number: number;
  speaker_id: string | null;
  speaker_name: string | null;
  start_time: number;
  end_time: number;
  text: string;
  confidence: number | null;
}

export interface Transcript {
  id: string;
  meeting_id: string;
  language: string | null;
  model_used: string | null;
  word_count: number;
  created_at: string;
  segments: TranscriptSegment[];
}

export interface Attendee {
  speaker_id: string | null;
  name: string;
  is_guest: boolean;
}

export interface KeyPoint {
  topic: string | null;
  description: string;
  importance: number | null;
}

export interface Decision {
  description: string;
  made_by: string | null;
  consensus: boolean;
}

export interface ActionItem {
  description: string;
  assignee: string | null;
  due_date: string | null;
  status: "pending" | "in_progress" | "done";
}

export interface Summary {
  id: string;
  meeting_id: string;
  model_used: string;
  ai_title: string | null;
  ai_date: string | null;
  next_agenda: string | null;
  additional_notes: string | null;
  formal_minutes: string | null;
  created_at: string;
  updated_at: string;
  attendees: Attendee[];
  key_points: KeyPoint[];
  decisions: Decision[];
  action_items: ActionItem[];
}

export interface SearchResultItem {
  meeting_id: string;
  title: string | null;
  date: string | null;
  status: string;
  team_id: string | null;
  created_at: string;
  matched_text: string;
  match_type: "transcript" | "summary" | "title";
}

export interface SearchResponse {
  items: SearchResultItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuthGroupMapping {
  id: string;
  auth_provider: string;
  group_name: string;
  mapped_role: string;
  team_id: string | null;
  created_at: string;
}
