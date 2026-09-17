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
};

export type Stats = {
  group: string;
  days: number;
  total_posts: number;
  new_since_yesterday: number;
  last_fetched: string | null;
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
