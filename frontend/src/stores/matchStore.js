import { defineStore } from "pinia";
import { request } from "@/utils/http";

export const useMatchStore = defineStore("matchStore", {
  state: () => ({
    matches: [],
    total: 0,
    page: 1,
    pageSize: 10,
    loading: false,
    hasMore: true,
    filterDate: "",
    filterLeague: "",
    error: "",
    playsData: null,
    playsLoading: false,
    playsError: "",
  }),
  getters: {},
  actions: {
    async refreshMatches() {
      this.page = 1;
      this.matches = [];
      this.total = 0;
      this.hasMore = true;
      await this.fetchMatches();
    },
    async fetchMatches() {
      if (this.loading) return;
      this.loading = true;
      this.error = "";
      try {
        const data = await request({
          url: "/api/matches",
          method: "GET",
          data: {
            league: this.filterLeague || undefined,
            page_size: 50,
          },
        });
        // 接口一次性返回所有数据
        const items = data?.items || data || [];
        this.matches = Array.isArray(items) ? items : [];
        this.total = this.matches.length;
        this.hasMore = false;
      } catch (err) {
        this.error = err?.message || "加载失败";
        this.hasMore = false;
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (!this.loading && this.hasMore) {
        await this.fetchMatches();
      }
    },
    async fetchPlays(matchId) {
      this.playsLoading = true;
      this.playsError = "";
      try {
        const data = await request({ url: `/api/matches/${matchId}/plays` });
        this.playsData = data;
      } catch (err) {
        this.playsError = err?.message || "玩法加载失败";
      } finally {
        this.playsLoading = false;
      }
    },
    clearPlays() {
      this.playsData = null;
      this.playsError = "";
    },
  },
});
