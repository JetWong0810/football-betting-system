<script setup>
import { onLaunch, onShow } from "@dcloudio/uni-app";
import { useBetStore } from "@/stores/betStore";
import { useConfigStore } from "@/stores/configStore";

const betStore = useBetStore();
const configStore = useConfigStore();

onLaunch(async () => {
  await configStore.bootstrap();
  await betStore.bootstrap();
});

onShow(() => {
  betStore.recalculateSnapshots();
});
</script>

<style lang="scss">
@import "./uni.scss";

page {
  background-color: $frbt-bg;
  font-family: "Source Sans Pro", "Helvetica Neue", Arial, sans-serif;
  color: $frbt-text;
  padding-bottom: 0;
}
</style>
