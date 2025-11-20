import { defineStore } from "pinia";
import { computed, ref } from "vue";
import dayjs from "dayjs";
import { useConfigStore } from "./configStore";
import { request } from "@/utils/http";

const defaultBet = () => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  matchName: "",
  league: "",
  betType: "win-draw-lose",
  wagerType: "single",
  stake: 0,
  odds: 1.0,
  platform: "",
  result: "pending",
  status: "saved", // saved: 已保存(草稿), betting: 投注中, settled: 已结算
  profit: 0,
  fee: 0,
  betTime: dayjs().format("YYYY-MM-DD HH:mm"),
  tags: [],
  note: "",
  legs: [],
});

export const useBetStore = defineStore("bet", () => {
  const bets = ref([]); // 所有已加载的记录（用于统计和展示）
  const loading = ref(false);
  const snapshots = ref([]);

  // 分页相关状态
  const page = ref(1);
  const pageSize = ref(20);
  const total = ref(0);
  const hasMore = ref(true);

  // 计算总投注金额（只统计投注中和已结算的）
  const totalStake = computed(() => bets.value.filter((bet) => bet.status === "betting" || bet.status === "settled").reduce((sum, bet) => sum + Number(bet.stake || 0), 0));

  // 计算总盈亏（只统计已结算的）
  const totalProfit = computed(() => bets.value.filter((bet) => bet.status === "settled").reduce((sum, bet) => sum + Number(bet.profit || 0), 0));

  // 统计胜负场次（只统计已结算的）
  const winCount = computed(() => bets.value.filter((bet) => bet.status === "settled" && bet.result === "win").length);
  const loseCount = computed(() => bets.value.filter((bet) => bet.status === "settled" && bet.result === "lose").length);

  // 胜率计算（只统计已结算的）
  const winningRate = computed(() => {
    const settledBets = bets.value.filter((bet) => bet.status === "settled");
    if (!settledBets.length) return 0;
    return winCount.value / settledBets.length;
  });

  const consecutiveLosses = computed(() => {
    let streak = 0;
    const settledBets = bets.value.filter((bet) => bet.status === "settled");
    for (const bet of settledBets) {
      if (bet.result === "lose") {
        streak += 1;
      } else if (bet.result === "win") {
        break;
      }
    }
    return streak;
  });

  // 当前余额 = 初始资金 + 已结算盈亏 - 投注中金额
  const bankroll = computed(() => {
    const configStore = useConfigStore();
    const bettingStake = bets.value.filter((bet) => bet.status === "betting").reduce((sum, bet) => sum + Number(bet.stake || 0), 0);
    return Number(configStore.startingCapital) + totalProfit.value - bettingStake;
  });

  function recalculateSnapshots() {
    const grouped = bets.value.reduce((acc, bet) => {
      const dayKey = dayjs(bet.betTime).format("YYYY-MM-DD");
      if (!acc[dayKey]) {
        acc[dayKey] = { date: dayKey, stake: 0, profit: 0 };
      }
      acc[dayKey].stake += Number(bet.stake || 0);
      acc[dayKey].profit += Number(bet.profit || 0);
      return acc;
    }, {});
    snapshots.value = Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date));
  }

  /**
   * 将数据库返回的数据格式转换为前端使用的格式
   * 数据库格式：{ id, bet_data (JSON), bet_time, status, result, stake, odds, profit, ... }
   * 前端格式：{ id, matchName, league, betType, wagerType, stake, odds, ... }
   */
  function normalizeBetFromDB(dbRecord) {
    if (!dbRecord) return null;

    // 从 bet_data JSON 中提取所有字段
    const betData = dbRecord.bet_data || {};

    // 处理时间格式：数据库返回的可能是 'YYYY-MM-DD HH:mm:ss'，转换为 'YYYY-MM-DD HH:mm'
    let betTime = dbRecord.bet_time || betData.betTime;
    if (betTime) {
      // 如果是完整的时间戳格式，截取到分钟
      if (betTime.length > 16) {
        betTime = betTime.substring(0, 16);
      }
    } else {
      betTime = dayjs().format("YYYY-MM-DD HH:mm");
    }

    // 合并数据库字段和 bet_data 中的字段
    // 注意：数据库ID优先，放在最后以确保不被覆盖
    const normalized = {
      ...betData, // bet_data 中的所有字段
      // 数据库直接存储的字段优先（放在后面会覆盖前面的）
      id: dbRecord.id, // 使用数据库ID（整数），覆盖betData中的字符串ID
      betTime: betTime,
      status: dbRecord.status || betData.status || "saved",
      result: dbRecord.result || betData.result || "pending",
      stake: Number(dbRecord.stake || betData.stake || 0),
      odds: Number(dbRecord.odds || betData.odds || 1),
      profit: dbRecord.profit !== null && dbRecord.profit !== undefined ? Number(dbRecord.profit) : betData.profit !== null && betData.profit !== undefined ? Number(betData.profit) : 0,
      created_at: dbRecord.created_at,
      updated_at: dbRecord.updated_at,
    };

    // 确保必要字段存在
    if (!normalized.legs || !Array.isArray(normalized.legs)) {
      normalized.legs = [];
    }
    if (!normalized.tags || !Array.isArray(normalized.tags)) {
      normalized.tags = [];
    }

    return normalized;
  }

  /**
   * 将前端格式的数据转换为数据库格式
   */
  function prepareBetForDB(bet) {
    // 提取需要存储在 bet_data JSON 中的字段
    const betData = {
      id: bet.id, // 保留前端生成的ID（用于临时标识）
      matchName: bet.matchName,
      league: bet.league,
      betType: bet.betType,
      wagerType: bet.wagerType,
      platform: bet.platform,
      fee: bet.fee || 0,
      tags: bet.tags || [],
      note: bet.note || "",
      legs: bet.legs || [],
    };

    return {
      bet_data: betData,
      bet_time: bet.betTime || dayjs().format("YYYY-MM-DD HH:mm:ss"),
      status: bet.status || "saved",
      result: bet.result || null,
      stake: Number(bet.stake || 0),
      odds: Number(bet.odds || 1),
      profit: bet.profit !== null && bet.profit !== undefined ? Number(bet.profit) : null,
    };
  }

  function normalizeBet(payload = {}) {
    const base = defaultBet();
    const draft = {
      ...base,
      ...payload,
      id: payload.id || base.id,
      status: payload.status || base.status, // 保留传入的status
    };

    const normalizedLegs = (() => {
      if (Array.isArray(payload.legs) && payload.legs.length) {
        return payload.legs.map((leg, index) => ({
          id: leg.id || `${draft.id}-leg-${index}`,
          homeTeam: leg.homeTeam || "",
          awayTeam: leg.awayTeam || "",
          league: leg.league || payload.league || "",
          matchTime: leg.matchTime || payload.betTime || base.betTime,
          betType: leg.betType || payload.betType || "胜平负",
          odds: Number(leg.odds || 1),
          stake: Number(leg.stake || 0),
          selection: leg.selection || "",
          note: leg.note || "",
        }));
      }

      // 兼容旧数据：将单场信息转为一个 leg
      return [
        {
          id: `${draft.id}-leg-0`,
          homeTeam: payload.homeTeam || payload.matchName || "",
          awayTeam: payload.awayTeam || "",
          league: payload.league || "",
          matchTime: payload.betTime || base.betTime,
          betType: payload.betType || "胜平负",
          odds: Number(payload.odds || 1),
          stake: Number(payload.stake || 0),
          selection: "",
          note: payload.note || "",
        },
      ];
    })();

    const legsCount = normalizedLegs.length;
    const oddsFromLegs = normalizedLegs.reduce((acc, leg) => acc * (Number(leg.odds) || 1), 1);
    const stake = Number(draft.stake || 0);
    const fee = Number(draft.fee || 0);
    const odds = Number(draft.odds || oddsFromLegs || 1);

    draft.legs = normalizedLegs;
    draft.odds = odds;
    draft.wagerType = payload.wagerType || (legsCount > 1 ? "parlay" : "single");
    draft.betType = draft.wagerType === "parlay" || legsCount > 1 ? `串关(${legsCount})` : normalizedLegs[0].betType || "胜平负";
    draft.league = legsCount === 1 ? normalizedLegs[0].league : "串关";
    draft.matchName = (() => {
      if (legsCount === 1) {
        const leg = normalizedLegs[0];
        if (leg.homeTeam && leg.awayTeam) {
          return `${leg.homeTeam} vs ${leg.awayTeam}`;
        }
        return leg.homeTeam || leg.awayTeam || payload.matchName || "未命名比赛";
      }
      const firstLeg = normalizedLegs[0];
      const anchor = firstLeg.homeTeam || firstLeg.awayTeam || firstLeg.league || "多场串关";
      return `${anchor} 等${legsCount}场`;
    })();
    draft.wagerType = draft.wagerType || (legsCount > 1 ? "parlay" : "single");

    // 只有已结算状态才计算盈亏
    if (draft.status === "settled") {
      if (draft.result === "win") {
        draft.profit = stake * (odds - 1) - fee;
      } else if (draft.result === "lose") {
        draft.profit = -stake - fee;
      } else if (draft.result === "half-win") {
        draft.profit = (stake * (odds - 1)) / 2 - fee;
      } else if (draft.result === "half-lose") {
        draft.profit = -stake / 2 - fee;
      } else {
        draft.profit = 0;
      }
    } else {
      draft.profit = 0; // 未结算的记录盈亏为0
    }

    return draft;
  }

  /**
   * 从数据库加载投注记录（分页）
   */
  async function fetchBets(reset = false) {
    if (loading.value) return;

    loading.value = true;
    try {
      const currentPage = reset ? 1 : page.value;
      // GET 请求使用查询参数，而不是 data
      const queryParams = new URLSearchParams({
        page: String(currentPage),
        page_size: String(pageSize.value),
      }).toString();
      const data = await request({
        url: `/api/bets?${queryParams}`,
        method: "GET",
      });

      if (data && data.items && Array.isArray(data.items)) {
        const newBets = data.items
          .map(normalizeBetFromDB)
          .filter((bet) => bet !== null)
          .map(normalizeBet); // 再次标准化以确保格式一致

        if (reset) {
          bets.value = newBets;
          page.value = 1;
        } else {
          // 追加新记录，避免重复
          const existingIds = new Set(bets.value.map((b) => b.id));
          const uniqueNewBets = newBets.filter((b) => !existingIds.has(b.id));
          bets.value = [...bets.value, ...uniqueNewBets];
        }

        // 更新分页信息
        total.value = data.total || 0;
        hasMore.value = bets.value.length < total.value;

        if (!reset && newBets.length > 0) {
          page.value = currentPage + 1;
        }
      } else {
        if (reset) {
          bets.value = [];
        }
        total.value = 0;
        hasMore.value = false;
      }
    } catch (error) {
      console.error("加载投注记录失败:", error);
      // 如果未登录或token失效，返回空数组
      if (error.statusCode === 401) {
        if (reset) {
          bets.value = [];
        }
        total.value = 0;
        hasMore.value = false;
      }
    } finally {
      loading.value = false;
      recalculateSnapshots();
    }
  }

  /**
   * 刷新投注记录（重置到第一页）
   */
  async function refreshBets() {
    page.value = 1;
    hasMore.value = true;
    await fetchBets(true);
  }

  /**
   * 加载更多投注记录
   */
  async function loadMore() {
    if (!hasMore.value || loading.value) return;
    await fetchBets(false);
  }

  /**
   * 从数据库加载投注记录（兼容旧接口，用于初始化）
   */
  async function bootstrap() {
    await refreshBets();
  }

  /**
   * 添加投注记录（异步，保存到数据库）
   */
  async function addBet(payload) {
    const bet = normalizeBet(payload);

    // 如果是投注中状态，检查余额是否足够
    if (bet.status === "betting") {
      const configStore = useConfigStore();
      const currentBalance = bankroll.value;
      if (currentBalance < bet.stake) {
        throw new Error("账户余额不足");
      }
    }

    try {
      // 准备数据库格式的数据
      const dbData = prepareBetForDB(bet);

      // 调用API创建记录
      const response = await request({
        url: "/api/bets",
        method: "POST",
        data: dbData,
      });

      // 使用数据库返回的ID更新bet对象
      bet.id = response.id;

      // 添加到本地列表（前端显示，插入到最前面）
      bets.value = [bet, ...bets.value];

      // 更新总数（如果当前已加载的记录数小于总数，说明还有未加载的记录）
      if (bets.value.length <= total.value) {
        total.value += 1;
      }

      recalculateSnapshots();

      return bet;
    } catch (error) {
      console.error("保存投注记录失败:", error);
      throw new Error(error.message || "保存投注记录失败");
    }
  }

  /**
   * 更新投注记录（异步，保存到数据库）
   */
  async function updateBet(id, payload) {
    const oldBet = bets.value.find((bet) => bet.id === id);
    if (!oldBet) {
      throw new Error("投注记录不存在");
    }

    // 如果从其他状态变为投注中，检查余额
    if (payload.status === "betting" && oldBet?.status !== "betting") {
      const currentBalance = bankroll.value;
      const stake = Number(payload.stake || oldBet?.stake || 0);
      if (currentBalance < stake) {
        throw new Error("账户余额不足");
      }
    }

    try {
      // 合并更新数据
      const updatedBet = normalizeBet({ ...oldBet, ...payload, id });

      // 准备数据库格式的数据
      const dbData = prepareBetForDB(updatedBet);

      // 调用API更新记录
      await request({
        url: `/api/bets/${id}`,
        method: "PUT",
        data: dbData,
      });

      // 更新本地列表
      bets.value = bets.value.map((bet) => {
        if (bet.id !== id) return bet;
        return updatedBet;
      });
      recalculateSnapshots();
    } catch (error) {
      console.error("更新投注记录失败:", error);
      throw new Error(error.message || "更新投注记录失败");
    }
  }

  /**
   * 删除投注记录（异步，从数据库删除）
   */
  async function removeBet(id) {
    try {
      // 调用API删除记录
      await request({
        url: `/api/bets/${id}`,
        method: "DELETE",
      });

      // 从本地列表移除
      bets.value = bets.value.filter((bet) => bet.id !== id);

      // 更新总数
      if (total.value > 0) {
        total.value -= 1;
      }

      recalculateSnapshots();
    } catch (error) {
      console.error("删除投注记录失败:", error);
      throw new Error(error.message || "删除投注记录失败");
    }
  }

  /**
   * 将投注记录从"投注中"结算（异步，保存到数据库）
   */
  async function settleBet(id, result) {
    const bet = bets.value.find((b) => b.id === id);
    if (!bet) {
      throw new Error("投注记录不存在");
    }
    if (bet.status !== "betting") {
      throw new Error("只能结算投注中的记录");
    }

    await updateBet(id, {
      status: "settled",
      result: result || bet.result,
    });
  }

  /**
   * 清空所有投注记录（注意：这个操作不会删除数据库记录，只是清空本地列表）
   */
  function clearBets() {
    bets.value = [];
    recalculateSnapshots();
  }

  return {
    bets,
    loading,
    snapshots,
    totalStake,
    totalProfit,
    winCount,
    loseCount,
    winningRate,
    consecutiveLosses,
    bankroll,
    // 分页相关
    page,
    pageSize,
    total,
    hasMore,
    // 方法
    bootstrap,
    fetchBets,
    refreshBets,
    loadMore,
    addBet,
    updateBet,
    removeBet,
    clearBets,
    recalculateSnapshots,
    settleBet,
  };
});
