export const API = process.env.API_URL ?? "http://localhost:8000";

export type Post = {
  post_id: string;
  group_id: string;
  poster_name: string | null;
  body: string | null;
  created_at: string | null;
  fetched_at: string;
  reaction_count: number;
  comment_count: number;
  share_count: number;
  permalink: string | null;
  keywords: string[];
  sentiment: string | null;
  summary: string | null;
};

export type Stats = {
  group: string;
  days: number;
  total_posts: number;
  new_since_yesterday: number;
  last_fetched: string | null;
  sentiment: { label: string; count: number; pct: number }[];
  top_keywords: { word: string; count: number; pct: number }[];
  top_posters: { name: string; count: number }[];
  top_posts: {
    post_id: string;
    poster_name: string | null;
    snippet: string;
    created_at: string | null;
    engagement: number;
    permalink: string | null;
  }[];
};

export type PostsResponse = { total: number; posts: Post[] };

export type Group = { name: string; group_id: string };
export type GroupsResponse = { groups: Group[] };

export type CompareGroup = {
  name: string;
  group_id: string;
  sample_size: number;
  share_of_voice: number;
  avg_engagement: number;
  top_keywords: { word: string; count: number; pct: number }[];
  keyword_delta: {
    sample_size: { first_half: number; second_half: number };
    items: { word: string; first_half: number; second_half: number }[];
  };
};

export type CompareResponse = {
  days: number;
  total_posts: number;
  groups: CompareGroup[];
  shared_keywords: { word: string; count: number; in_groups: number }[];
};

export type TimelineBucket = {
  date: string;
  posts: number;
  engagement: number;
  top_keyword: string | null;
};

export type TimelineResponse = {
  group: string;
  days: number;
  timezone: string;
  buckets: TimelineBucket[];
};
