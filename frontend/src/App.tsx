import { useCallback, useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import {
  Leaf,
  LayoutDashboard,
  Radio,
  ChartNoAxesCombined,
  Bell,
  Sparkles,
  Database,
  FileCode2,
  ChevronDown,
  ArrowUpRight,
  Play,
  Pause,
  SkipForward,
  Clock3,
  Wind,
  Droplets,
  Thermometer,
  Activity,
  Check,
  Send,
  LoaderCircle,
  RefreshCw,
  Settings2,
  ExternalLink,
  Layers,
  Search,
  CheckCheck,
  ShieldCheck,
  X,
  CircleHelp,
  Maximize2,
} from "lucide-react";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
]);
type Obj = Record<string, any>;
const MENU = [
  ["overview", "总览驾驶舱", LayoutDashboard],
  ["sensors", "节点与趋势", Radio],
  ["forecast", "预测分析", ChartNoAxesCombined],
  ["alerts", "预警与处理", Bell],
  ["assistant", "智能助手", Sparkles],
  ["parameters", "环境设置", Settings2],
  ["settings", "数据与模型", Database],
] as const;
const LABELS: Obj = {
  normal: "环境正常",
  warning: "环境偏离",
  stale: "数据陈旧",
  invalid: "观测无效",
  missing: "暂无数据",
  pending: "待确认",
  confirmed: "已确认",
  observing: "待复看",
  closed: "已关闭",
  notice: "预测提示",
  acknowledged: "模拟执行成功",
};
async function api(path: string, options: RequestInit = {}) {
  const r = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!r.ok) {
    let j: Obj = {};
    try {
      j = await r.json();
    } catch {}
    throw new Error(
      typeof j.detail === "string"
        ? j.detail
        : "操作未完成，请检查输入或稍后重试",
    );
  }
  return r.json();
}
const post = (p: string, b: Obj = {}) =>
  api(p, { method: "POST", body: JSON.stringify(b) });
const val = (x: any, d = 1) =>
  x === null || x === undefined ? "—" : Number(x).toFixed(d);
const time = (t: string | undefined) =>
  t ? t.replace("T", " ").slice(0, 19) : "暂无观测";
function useQuery(path: string, interval = 0) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(
    () =>
      api(path)
        .then((x) => {
          setData(x);
          setError("");
        })
        .catch((e) => setError(e.message)),
    [path],
  );
  useEffect(() => {
    refresh();
    if (interval) {
      const t = setInterval(refresh, interval);
      return () => clearInterval(t);
    }
  }, [refresh, interval]);
  return { data, error, refresh };
}
function Badge({
  children,
  tone = "green",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={"badge " + tone}>{children}</span>;
}
function Panel({
  title,
  sub,
  action,
  children,
  className = "",
}: {
  title: string;
  sub?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={"glass panel " + className}>
      <div className="panel-head">
        <div>
          <h3>{title}</h3>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <CircleHelp size={25} />
      <p>{children}</p>
    </div>
  );
}
function Chart({
  points = [],
  pred = [],
  metric = "temperature",
  height = 270,
  threshold,
}: {
  points: Obj[];
  pred?: Obj[];
  metric?: string;
  height?: number;
  threshold?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const unit =
      metric === "temperature"
        ? "℃"
        : metric === "humidity"
          ? "%"
          : metric === "vpd"
            ? "kPa"
            : metric === "rssi"
              ? "dBm"
              : "dB";
    const color =
      metric === "humidity"
        ? "#4787aa"
        : metric === "vpd"
          ? "#8a63a1"
          : "#608b39";
    const observed = points.map((v) => [v.time, v[metric]]);
    const forecast = pred.length
      ? [
          ...(points.length
            ? [
                [
                  points[points.length - 1].time,
                  points[points.length - 1][metric],
                ],
              ]
            : []),
          ...pred.map((v) => [v.time, v[metric]]),
        ]
      : [];
    chart.setOption({
      backgroundColor: "transparent",
      textStyle: { fontFamily: "Inter,Microsoft YaHei,sans-serif" },
      grid: { left: 42, right: 22, top: 24, bottom: 38 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#12292d",
        borderColor: "#395153",
        textStyle: { color: "#e6efea" },
        valueFormatter: (x: any) =>
          x == null ? "缺失" : val(x, 2) + " " + unit,
      },
      legend: {
        show: pred.length > 0,
        top: 0,
        right: 18,
        textStyle: { color: "#5c7058" },
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: "#bac8ab" } },
        axisTick: { show: false },
        axisLabel: { color: "#5c7058", formatter: "{HH}:{mm}" },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        name: unit,
        nameTextStyle: { color: "#5c7058" },
        splitLine: {
          lineStyle: { color: "rgba(71,105,50,.14)", type: "dashed" },
        },
        axisLabel: { color: "#5c7058" },
      },
      series: [
        {
          name: "真实观测",
          type: "line",
          data: observed,
          smooth: false,
          connectNulls: false,
          showSymbol: false,
          lineStyle: { width: 2.4, color },
          itemStyle: { color },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {
                offset: 0,
                color:
                  metric === "humidity"
                    ? "rgba(143,207,244,.20)"
                    : "rgba(183,245,132,.22)",
              },
              { offset: 1, color: "rgba(183,245,132,0)" },
            ]),
          },
          markLine:
            threshold == null
              ? undefined
              : {
                  silent: true,
                  symbol: "none",
                  label: { formatter: "配置参考线", color: "#9c794b" },
                  lineStyle: { color: "#9c794b", type: "dashed" },
                  data: [{ yAxis: threshold }],
                },
        },
        {
          name: "GRU预测",
          type: "line",
          data: forecast,
          showSymbol: true,
          symbolSize: 5,
          lineStyle: { width: 2, color: "#b77b3b", type: "dashed" },
          itemStyle: { color: "#b77b3b" },
        },
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [points, pred, metric, threshold]);
  return (
    <div
      ref={ref}
      style={{ height, width: "100%" }}
      aria-label="真实传感器数据趋势图"
    />
  );
}
function Greenhouse({
  nodes,
  selected,
  onSelect,
}: {
  nodes: Obj[];
  selected: string;
  onSelect: (n: string) => void;
}) {
  return (
    <div className="greenhouse-view">
      <div className="scene-caption">
        <span className="live-dot" />
        温室 01 <span>· 3 × 9 相对部署示意</span>
      </div>
      <svg
        viewBox="0 0 1000 445"
        role="group"
        aria-label="27个无线传感器节点的温室布局，点击节点查看真实数据"
      >
        <defs>
          <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#cbdab9" stopOpacity=".65" />
            <stop offset="1" stopColor="#b6c9a5" stopOpacity=".35" />
          </linearGradient>
          <linearGradient id="roof">
            <stop stopColor="#c8e7da" stopOpacity=".04" />
            <stop offset="1" stopColor="#c8e7da" stopOpacity=".10" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>
        <path
          d="M45 150 L500 24 L955 150 L955 364 L45 364Z"
          fill="url(#roof)"
          stroke="#9ec5b5"
          strokeOpacity=".22"
        />
        <path
          d="M45 150 L45 364 L955 364 L955 150 M500 24V160 M45 150L500 160L955 150"
          fill="none"
          stroke="#9ec5b5"
          strokeOpacity=".2"
        />
        <path d="M45 364L500 434L955 364L500 294Z" fill="url(#floor)" />
        {[140, 320, 500, 680, 860].map((x) => (
          <path
            key={x}
            d={`M${x} 110 L${x} 364`}
            stroke="#a4cab9"
            strokeOpacity=".11"
            strokeDasharray="4 5"
          />
        ))}
        {[0, 1, 2].map((r) => (
          <g key={r}>
            <rect
              x="76"
              y={145 + r * 78}
              width="848"
              height="56"
              rx="24"
              fill="#dce6c9"
              stroke="#8ca875"
              strokeOpacity=".3"
            />
            {Array.from({ length: 18 }, (_, j) => (
              <g key={j} opacity=".55">
                <path
                  d={`M${97 + j * 46} ${178 + r * 78}v-19`}
                  stroke="#629064"
                  strokeWidth="2"
                />
                <ellipse
                  cx={92 + j * 46}
                  cy={165 + r * 78}
                  rx="8"
                  ry="4"
                  transform={`rotate(28 ${92 + j * 46} ${165 + r * 78})`}
                  fill="#52875c"
                />
                <ellipse
                  cx={102 + j * 46}
                  cy={158 + r * 78}
                  rx="8"
                  ry="4"
                  transform={`rotate(-25 ${102 + j * 46} ${158 + r * 78})`}
                  fill="#78a06b"
                />
                <circle
                  cx={100 + j * 46}
                  cy={173 + r * 78}
                  r="3"
                  fill="#b56a4e"
                />
              </g>
            ))}
          </g>
        ))}
        {nodes.map((n) => {
          let x = 104 + n.col_index * 99,
            y = 155 + n.row_index * 78;
          const active = n.id === selected;
          const color =
            n.state === "warning"
              ? "#b67537"
              : n.state === "normal"
                ? "#438563"
                : "#829393";
          return (
            <g
              key={n.id}
              className="sensor-node"
              tabIndex={0}
              role="button"
              aria-label={`${n.id} ${LABELS[n.state]} ${val(n.temperature)}摄氏度`}
              onClick={() => onSelect(n.id)}
              onKeyDown={(e) =>
                (e.key === "Enter" || e.key === " ") && onSelect(n.id)
              }
            >
              <title>
                {n.id} · {LABELS[n.state]} · {val(n.temperature)}℃
              </title>
              <circle
                cx={x}
                cy={y}
                r={active ? 26 : 20}
                fill={color}
                opacity={active ? 0.12 : 0.04}
              />
              <circle
                cx={x}
                cy={y}
                r={active ? 20 : 14}
                fill="#eff4e8"
                stroke={color}
                strokeWidth={active ? 2 : 1}
                strokeOpacity={active ? 1 : 0.6}
              />
              <path
                d={`M${x - 6} ${y - 1}q6-8 12 0m-10 3q4-5 8 0`}
                fill="none"
                stroke={color}
                strokeWidth="1.4"
              />
              <circle cx={x} cy={y + 5} r="1.5" fill={color} />
              <text
                x={x}
                y={y + 36}
                textAnchor="middle"
                fill={active ? "#2c4937" : "#4f6552"}
                fontSize="15"
                fontWeight={active ? "700" : "400"}
              >
                {n.id}
              </text>
              {active && (
                <g>
                  <rect
                    x={x - 36}
                    y={y - 50}
                    width="72"
                    height="25"
                    rx="7"
                    fill="#e1eccb"
                  />
                  <text
                    x={x}
                    y={y - 33}
                    textAnchor="middle"
                    fill="#163322"
                    fontSize="16"
                    fontWeight="700"
                  >
                    {val(n.temperature)} ℃
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
      <div className="scene-legend">
        <span>
          <i style={{ background: "#b9ed91" }} />
          环境正常
        </span>
        <span>
          <i style={{ background: "#edc18a" }} />
          环境偏离
        </span>
        <span>
          <i style={{ background: "#829393" }} />
          陈旧 / 无数据
        </span>
        <small>点击节点查看详情</small>
      </div>
    </div>
  );
}

function Workspace({ user, onLogout }: { user: Obj; onLogout: () => void }) {
  const [page, setPage] = useState("overview"),
    [node, setNode] = useState("AF34"),
    [metric, setMetric] = useState("temperature");
  const overview = useQuery("/overview", 3000),
    series = useQuery(`/nodes/${node}/series?hours=8`, 6000),
    pred = useQuery(`/forecast/${node}`, 9000),
    alerts = useQuery("/alerts", 5000),
    cfg = useQuery("/settings");
  const [toast, setToast] = useState(""),
    [clock, setClock] = useState("2020-06-25T13:45"),
    [busy, setBusy] = useState(false),
    [event, setEvent] = useState<Obj | null>(null);
  const [showNode, setShowNode] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const o = overview.data,
    selected = o?.nodes?.find((v: Obj) => v.id === node),
    activeTitle = MENU.find((m) => m[0] === page)?.[1];
  const notify = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 4500);
  };
  const refresh = () => {
    overview.refresh();
    series.refresh();
    pred.refresh();
    alerts.refresh();
    cfg.refresh();
  };
  async function control(action: string, extra: Obj = {}) {
    try {
      await post("/replay/control", { action, ...extra });
      refresh();
    } catch (e: any) {
      notify(e.message);
    }
  }
  const select = (id: string) => {
    setNode(id);
    setShowNode(true);
  };
  const showAssistant = (n: string) => {
    setNode(n);
    setAssistantOpen(true);
    setShowNode(false);
  };
  return (
    <div className="app-shell">
      <div className="photo-backdrop" />
      <div className="ambient ambient-a" />
      <div className="ambient ambient-b" />
      <aside className="sidebar glass">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <span className="brand-symbol">
            <Leaf size={24} />
          </span>
          <span>
            Verdant<small>温室智能环境平台</small>
          </span>
          <span className="brand-period">.</span>
        </a>

        <nav>
          {MENU.filter(([id]) =>
            user.role === "grower"
              ? id !== "settings"
              : !["alerts", "parameters"].includes(id),
          ).map(([id, title, Icon]) => (
            <button
              key={id}
              aria-label={title}
              className={"nav-item " + (page === id ? "active" : "")}
              onClick={() => setPage(id)}
            >
              <Icon size={19} />
              <span>{title}</span>
              {id === "alerts" && o?.metrics.open_alerts > 0 && (
                <em>{o.metrics.open_alerts}</em>
              )}
              {id === "assistant" && <span className="ai-tag">AI</span>}
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <div className="dataset-label">
            <Database size={17} />
            <div>
              真实 LoRaWAN 数据<small>Greenhouse-1 · 27 节点</small>
            </div>
          </div>
          <div className="side-user">
            <span>{user.role === "grower" ? "管" : "维"}</span>
            <div>
              {user.display_name}
              <small>{user.username}</small>
            </div>
            <button className="text-button logout-button" onClick={onLogout}>
              退出
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumbs">
            工作空间 <span>/</span> {activeTitle}
          </div>
          <div className="top-right">
            <span className="connection">
              <i />
              本地系统已连接
            </span>
            <span className="divider" />
            <Badge tone="neutral">历史数据回放</Badge>
            <span className="avatar">Z</span>
          </div>
        </header>
        <div className="page-title">
          <div>
            <h1>{page === "overview" ? "温室总览" : activeTitle}</h1>
          </div>
          <div className="title-right">
            <div className="greenhouse-picker">
              <Leaf size={17} />
              <span>番茄温室 01</span>
              <ChevronDown size={16} />
            </div>
          </div>
        </div>
        <div className="replay-toolbar glass">
          <div className="replay-time">
            <Clock3 size={17} />
            <span>源时间</span>
            <strong>{time(o?.replay.cursor)}</strong>
          </div>
          {user.role === "operator" && (
            <div className="replay-actions">
              <button
                aria-label={o?.replay.running ? "暂停回放" : "播放回放"}
                className="icon-button play-button"
                onClick={() => control(o?.replay.running ? "pause" : "play")}
              >
                {o?.replay.running ? <Pause size={16} /> : <Play size={16} />}
              </button>
              <button
                className="icon-button"
                aria-label="前进五分钟"
                onClick={() => control("step")}
              >
                <SkipForward size={17} />
              </button>
              <select
                aria-label="回放倍速"
                value={o?.replay.speed ?? 60}
                onChange={(e) =>
                  control("speed", { speed: Number(e.target.value) })
                }
              >
                {[1, 60, 300, 600, 1800].map((n) => (
                  <option key={n} value={n}>
                    {n}× 倍速
                  </option>
                ))}
              </select>
              <div className="toolbar-date">
                <input
                  aria-label="选择历史时间"
                  type="datetime-local"
                  value={clock}
                  onChange={(e) => setClock(e.target.value)}
                />
                <button
                  className="text-button"
                  onClick={() => control("seek", { cursor: clock })}
                >
                  跳转
                </button>
              </div>
            </div>
          )}
        </div>
        {overview.error && <div className="notice error">{overview.error}</div>}
        {o && !o.data_ready && user.role === "operator" && (
          <div className="notice">
            尚未导入原始记录。
            <button className="text-button" onClick={() => setPage("settings")}>
              进入数据设置完成导入 →
            </button>
          </div>
        )}
        {page === "overview" && (
          <>
            <div className="metric-grid compact-metrics">
              {[
                {
                  label: "平均空气温度",
                  value: o?.metrics.temperature,
                  unit: "℃",
                  Icon: Thermometer,
                },
                {
                  label: "平均相对湿度",
                  value: o?.metrics.humidity,
                  unit: "%",
                  Icon: Droplets,
                },
                {
                  label: "平均空气VPD",
                  value: o?.metrics.vpd,
                  unit: "kPa",
                  Icon: Wind,
                },
                {
                  label: "有效数据节点",
                  value: o?.metrics.fresh_nodes,
                  unit: "/ 27",
                  Icon: Radio,
                },
              ].map(({ label, value, unit, Icon }) => (
                <div className="glass metric-card" key={label}>
                  <div className="metric-label">
                    {label}
                    <Icon size={20} />
                  </div>
                  <div className="metric-value">
                    {val(
                      value,
                      label.includes("节点")
                        ? 0
                        : label.includes("VPD")
                          ? 2
                          : 1,
                    )}
                    <small>{unit}</small>
                  </div>
                </div>
              ))}
            </div>
            <Panel
              title="温室感知全景"
              sub="27个真实节点 · 点击节点打开数据详情"
              action={<Badge>真实数据回放</Badge>}
              className="scene-panel panorama-panel"
            >
              <div className="panorama-stage" ref={stageRef}>
                <button
                  className="button secondary fullscreen-button"
                  aria-label="切换温室全屏"
                  onClick={() =>
                    document.fullscreenElement
                      ? document.exitFullscreen()
                      : stageRef.current?.requestFullscreen()
                  }
                >
                  <Maximize2 size={18} />
                  全屏查看
                </button>
                <Greenhouse
                  nodes={o?.nodes || []}
                  selected={showNode ? node : ""}
                  onSelect={select}
                />
                {showNode && (
                  <div
                    className="node-popup glass"
                    role="dialog"
                    aria-label="节点详情"
                  >
                    <div className="popup-head">
                      <h3>{node} · 节点详情</h3>
                      <button
                        className="icon-button"
                        aria-label="关闭节点详情"
                        onClick={() => setShowNode(false)}
                      >
                        <X size={19} />
                      </button>
                    </div>
                    <Badge
                      tone={
                        selected?.state === "normal"
                          ? "green"
                          : selected?.state === "warning"
                            ? "sand"
                            : "neutral"
                      }
                    >
                      {LABELS[selected?.state] || "暂无数据"}
                    </Badge>
                    <div className="popup-temperature">
                      {val(selected?.temperature)}
                      <small>℃</small>
                    </div>
                    <div className="detail-pair">
                      <div>
                        <span>相对湿度</span>
                        <strong>
                          {val(selected?.humidity)} <small>%</small>
                        </strong>
                      </div>
                      <div>
                        <span>空气VPD</span>
                        <strong>
                          {val(selected?.vpd, 2)} <small>kPa</small>
                        </strong>
                      </div>
                    </div>
                    <div className="signal-row">
                      <span>RSSI</span>
                      <strong>{val(selected?.rssi, 0)} dBm</strong>
                    </div>
                    <div className="signal-row">
                      <span>SNR</span>
                      <strong>{val(selected?.snr)} dB</strong>
                    </div>
                    <p className="popup-time">
                      最近源时间
                      <br />
                      {time(selected?.event_time)}
                    </p>
                    <button
                      className="button secondary full"
                      onClick={() => {
                        setPage("sensors");
                        setShowNode(false);
                      }}
                    >
                      查看该节点历史曲线 <ArrowUpRight size={16} />
                    </button>
                    <button
                      className="button primary full"
                      onClick={() => showAssistant(node)}
                    >
                      <Sparkles size={16} />
                      询问此节点
                    </button>
                  </div>
                )}
              </div>
            </Panel>
            <Panel
              title="当前待关注"
              sub="查看事件详情后确认处理"
              action={
                <button
                  className="text-button"
                  onClick={() => setPage("alerts")}
                >
                  查看全部事件 <ArrowUpRight size={15} />
                </button>
              }
            >
              <div className="home-events">
                {(o?.alerts || []).slice(0, 4).map((a: Obj) => (
                  <button
                    key={a.id}
                    onClick={() => {
                      setEvent(a);
                      setPage("alerts");
                    }}
                  >
                    <Bell size={18} />
                    <div>
                      <strong>{a.title}</strong>
                      <small>
                        {a.node_id} · {LABELS[a.status]}
                      </small>
                    </div>
                    <ArrowUpRight size={16} />
                  </button>
                ))}
                {!o?.alerts?.length && <span>暂无待处理事件</span>}
              </div>
            </Panel>
          </>
        )}
        {page === "sensors" && (
          <SensorHistoryPage
            node={node}
            setNode={setNode}
            nodes={o?.nodes || []}
            cursor={o?.replay.cursor}
            onAssistant={showAssistant}
          />
        )}
        {page === "forecast" && (
          <ForecastPage
            node={node}
            setNode={setNode}
            nodes={o?.nodes || []}
            points={series.data?.points || []}
            pred={pred.data}
            cfg={cfg.data}
            notify={notify}
            onRefresh={refresh}
            technical={user.role==="operator"}
          />
        )}
        {page === "alerts" && (
          <AlertsPage
            alerts={alerts.data || []}
            event={event}
            setEvent={setEvent}
            notify={notify}
            refresh={refresh}
            onAssistant={showAssistant}
            readOnly={user.role !== "grower"}
          />
        )}
        {page === "assistant" && (
          <AssistantPage
            node={node}
            setNode={setNode}
            nodes={o?.nodes || []}
            cursor={o?.replay.cursor}
            event={event}
            notify={notify}
          />
        )}
        {page === "parameters" && (
          <EnvironmentParameters
            cfg={cfg.data}
            notify={notify}
            refresh={refresh}
          />
        )}
        {page === "settings" && user.role === "operator" && (
          <SettingsPage cfg={cfg.data} notify={notify} refresh={refresh} />
        )}
        <footer>
          <span>
            <Leaf size={13} />
            VERDANT · 无线传感器环境智能应用
          </span>
          <span>
            真实观测回放 / 虚拟执行器模拟 <span className="footer-dot">·</span>{" "}
            周玮
          </span>
        </footer>
      </main>
      {page !== "assistant" && (
        <button
          className="assistant-fab"
          aria-label="打开AI助手"
          onClick={() => setAssistantOpen((v) => !v)}
        >
          <Sparkles size={24} />
          <span>问问 AI</span>
        </button>
      )}
      {assistantOpen && (
        <aside
          className="ai-drawer glass"
          role="dialog"
          aria-label="悬浮AI助手"
        >
          <div className="ai-drawer-head">
            <h3>
              <Sparkles size={20} />
              证据助手 · {node}
            </h3>
            <button
              className="icon-button"
              aria-label="关闭AI助手"
              onClick={() => setAssistantOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
          <AssistantPage
            node={node}
            setNode={setNode}
            nodes={o?.nodes || []}
            cursor={o?.replay.cursor}
            event={event}
            notify={notify}
          />
        </aside>
      )}
      {toast && (
        <div className="toast" role="status">
          <CheckCheck size={18} />
          {toast}
          <button className="icon-button" onClick={() => setToast("")}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

function ForecastPage({
  node,
  setNode,
  nodes,
  points,
  pred,
  cfg,
  notify,
  onRefresh,
  technical,
}: Obj) {
  const models = useQuery("/models", 4000);
  const active = models.data?.models?.find((m: Obj) => m.status === "active");
  return (
    <>
      <div className="forecast-intro glass">
        <div className="big-icon">
          <ChartNoAxesCombined size={29} />
        </div>
        <div>
          <h2>环境趋势预测</h2>
          <p>轻量 GRU 使用过去 2 小时，预测未来 30 分钟的温湿度。</p>
        </div>
        <Badge tone={pred?.status === "ready" ? "green" : "neutral"}>
          {pred?.status === "ready" ? "真实模型推理" : "预测暂停"}
        </Badge>
      </div>
      <div className="page-tools">
        <label>
          当前节点{" "}
          <select value={node} onChange={(e) => setNode(e.target.value)}>
            {nodes.map((n: Obj) => (
              <option key={n.id}>{n.id}</option>
            ))}
          </select>
        </label>
        <span>模型：{active?.id || "尚未训练"}</span>
      </div>
      {pred?.status !== "ready" && (
        <div className="notice">{pred?.reason || "正在检查模型与输入窗口"}</div>
      )}
      <div className="two-columns">
        {["temperature", "humidity"].map((metric) => (
          <Panel
            key={metric}
            title={
              metric === "temperature" ? "温度趋势与预测" : "湿度趋势与预测"
            }
            sub="实线为真实观测，虚线为GRU实际输出"
          >
            <Chart
              points={points}
              pred={pred?.points || []}
              metric={metric}
              height={320}
              threshold={cfg?.[metric + "_max"]}
            />
          </Panel>
        ))}
      </div>
      <div className="architecture-strip glass">
        {[
          ["24 × 6", "过去24步 / 6个输入通道"],
          ["GRU · 32", "共享单层门控循环单元"],
          ["6 × 2", "未来6步温度与湿度"],
          ["证据事件", "预测偏离 → 管理提示"],
        ].map(([a, b], i) => (
          <div key={a}>
            <strong>{a}</strong>
            <small>{b}</small>
            {i < 3 && <ArrowUpRight size={19} />}
          </div>
        ))}
      </div>
      {technical&&<Panel
        title="模型与数据状态"
        sub="训练段标准化；首70天范围内按共同时间轴切分，不跨时间段构造窗口"
      >
        <div className="model-detail">
          {active ? (
            <>
              <div>
                <small>真实训练时间</small>
                <strong>{time(active.trained_at)}</strong>
              </div>
              <div>
                <small>训练 / 验证边界</small>
                <strong>
                  {active.train_end.slice(0, 10)} /{" "}
                  {active.val_end.slice(0, 10)}
                </strong>
              </div>
              <div>
                <small>有效训练窗口</small>
                <strong>
                  {active.metrics.train_windows?.toLocaleString()}
                </strong>
              </div>
              <div>
                <small>实际训练轮数</small>
                <strong>{active.metrics.actual_epochs}</strong>
              </div>
            </>
          ) : (
            <Empty>还没有可用的模型权重，去数据设置启动本地训练。</Empty>
          )}
        </div>
      </Panel>}
    </>
  );
}

function AlertsPage({
  alerts,
  event,
  setEvent,
  notify,
  refresh,
  onAssistant,
  readOnly=false,
}: Obj) {
  const [filter, setFilter] = useState("all"),
    [note, setNote] = useState(""),
    [action, setAction] = useState("ventilate"),
    [busy, setBusy] = useState(false);
  const commands = useQuery("/commands", 5000);
  const chosen = alerts.find((a: Obj) => a.id === event?.id) || event;
  const list =
    filter === "all" ? alerts : alerts.filter((a: Obj) => a.status === filter);
  async function operate(kind: string) {
    if (!chosen) return;
    setBusy(true);
    try {
      await post(
        `/alerts/${chosen.id}/${kind}`,
        kind === "execute"
          ? { action, command_id: crypto.randomUUID(), note }
          : { note },
      );
      notify(
        kind === "confirm"
          ? "事件已人工确认"
          : kind === "execute"
            ? "虚拟设备已返回模拟执行回执"
            : "事件已关闭",
      );
      refresh();
      commands.refresh();
      setEvent({
        ...chosen,
        status:
          kind === "confirm"
            ? "confirmed"
            : kind === "execute"
              ? "observing"
              : "closed",
      });
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="alerts-layout">
      <Panel
        title={`预警事件 · ${alerts.length}`}
        sub="当前回放会话的全部事件"
        action={
          <select
            aria-label="筛选事件状态"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">全部状态</option>
            {["pending", "confirmed", "observing", "closed"].map((v) => (
              <option key={v} value={v}>
                {LABELS[v]}
              </option>
            ))}
          </select>
        }
      >
        <div className="event-list">
          {list.map((a: Obj) => (
            <button
              key={a.id}
              className={"event-row " + (a.id === chosen?.id ? "chosen" : "")}
              onClick={() => {
                setEvent(a);
                setNote(a.note || "");
              }}
            >
              <div>
                <Badge
                  tone={
                    a.type === "data_quality"
                      ? "neutral"
                      : a.type.startsWith("forecast")
                        ? "purple"
                        : "sand"
                  }
                >
                  {a.node_id}
                </Badge>
                <span>{a.title}</span>
                <Badge tone="neutral">{LABELS[a.status]}</Badge>
              </div>
              <small>
                {time(a.opened_at)} <ArrowUpRight size={13} />
              </small>
            </button>
          ))}
          {!list.length && <Empty>当前筛选下没有事件</Empty>}
        </div>
      </Panel>
      <Panel
        title="事件核对与处理"
        sub={
          chosen ? `${chosen.node_id} · ${chosen.id}` : "选择左侧事件查看依据"
        }
      >
        {chosen ? (
          <>
            <div className="event-heading">
              <h2>{chosen.title}</h2>
              <Badge tone="sand">{LABELS[chosen.status]}</Badge>
            </div>
            <dl className="evidence-facts">
              <div>
                <dt>触发时间</dt>
                <dd>{time(chosen.opened_at)}</dd>
              </div>
              <div>
                <dt>最近触发</dt>
                <dd>{time(chosen.last_seen)}</dd>
              </div>
              <div>
                <dt>证据来源</dt>
                <dd>{({actual_observation:"实际观测",derived_from_actual_T_RH:"实际温湿度",gru_prediction:"预测结果"} as Obj)[chosen.evidence?.source]||"数据质量"}</dd>
              </div>
            </dl>
            <details className="evidence-json">
              <summary>查看原始触发依据</summary>
              <pre>{JSON.stringify(chosen.evidence, null, 2)}</pre>
            </details>
            <button
              className="button secondary full"
              onClick={() => onAssistant(chosen.node_id)}
            >
              <Sparkles size={15} />让 AI 解释这条事件
            </button>
            <label className="form-label">
              人工核对与复看记录
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="记录判断、拟检查的设施，或关闭事件的依据……"
                rows={3}
              />
            </label>
            <label className="form-label">
              模拟处理动作
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
              >
                <option value="ventilate">模拟通风</option>
                <option value="open_window">模拟开窗</option>
                <option value="shade">模拟遮阳</option>
              </select>
            </label>
            <div className="button-row">
              <button
                className="button primary"
                disabled={busy || readOnly || chosen.status !== "pending"}
                onClick={() => operate("confirm")}
              >
                <Check size={15} />
                确认事件
              </button>
              <button
                className="button secondary"
                disabled={busy || readOnly || chosen.status !== "confirmed"}
                onClick={() => operate("execute")}
              >
                <Wind size={15} />
                执行模拟
              </button>
              <button
                className="button secondary"
                disabled={
                  busy || !["confirmed", "observing"].includes(chosen.status)
                }
                onClick={() => operate("close")}
              >
                复看并关闭
              </button>
            </div>

            <div className="command-feed">
              {commands.data
                ?.filter((c: Obj) => c.event_id === chosen.id)
                .map((c: Obj) => (
                  <div key={c.id}>
                    <CheckCheck size={16} />
                    <div>
                      模拟回执：{LABELS[c.status] || c.status}
                      <small>
                        {({ventilate:"模拟通风",open_window:"模拟开窗",shade:"模拟遮阳"} as Obj)[c.action]||c.action} · {time(c.ack_at)}
                      </small>
                    </div>
                  </div>
                ))}
            </div>
          </>
        ) : (
          <Empty>先选择一条预警事件</Empty>
        )}
      </Panel>
    </div>
  );
}

function AssistantPage({ node, setNode, nodes, cursor, event, notify }: Obj) {
  const [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState<Obj | null>(null),
    [busy, setBusy] = useState(false);
  const knowledge = useQuery("/knowledge");
  async function ask(q = question) {
    if (!q.trim()) return;
    setQuestion(q);
    setBusy(true);
    try {
      setAnswer(
        await post("/assistant/ask", {
          question: q,
          node_id: node,
          event_id: event?.node_id === node ? event.id : null,
          session_id: "browser",
        }),
      );
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="assistant-layout">
      <Panel
        title="温室证据助手"

        action={
          <Badge tone="purple">
            <Sparkles size={13} />
            DeepSeek + RAG
          </Badge>
        }
      >
        <div className="assistant-context">
          <label>
            上下文节点{" "}
            <select value={node} onChange={(e) => setNode(e.target.value)}>
              {nodes.map((n: Obj) => (
                <option key={n.id}>{n.id}</option>
              ))}
            </select>
          </label>
          <small>回放源时间：{time(cursor)}</small>
        </div>
        {!answer && !busy && (
          <div className="assistant-welcome">
            <span className="ai-orb">
              <Sparkles size={32} />
            </span>
            <h2>有什么需要了解？</h2>
            <p>关于节点变化、预警依据和检查建议，都可以从这里开始。</p>
            <div className="suggestions">
              {[
                `${node}当前温湿度如何，应该先检查什么？`,
                "为什么空气VPD要结合温度和湿度看？",
                "RSSI和SNR能说明什么，能判断丢包吗？",
              ].map((q) => (
                <button key={q} onClick={() => ask(q)}>
                  {q}
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
          </div>
        )}
        {busy && (
          <div className="thinking">
            <LoaderCircle className="spin" size={29} />
            <h3>正在检索和组织证据…</h3>
            <p>读取真实节点记录 → 混合检索 → 排序去重 → DeepSeek解释</p>
          </div>
        )}
        {answer && !busy && (
          <div className="answer-block">
            <div className="question-bubble">{question}</div>
            <div className="answer-provider">
              <Sparkles size={18} />
              <strong>{answer.provider_label}</strong>
              {answer.model && <span>{answer.model}</span>}
            </div>
            {answer.fallback_reason && (
              <div className="notice compact">
                {answer.fallback_reason}，本次使用可追溯的本地证据模板。
              </div>
            )}
            <div className="answer-text">{answer.answer}</div>
            <div className="answer-suggestions">
              <h4>建议检查步骤</h4>
              {answer.suggestions.map((s: string, i: number) => (
                <p key={i}>
                  <span>{i + 1}</span>
                  {s}
                </p>
              ))}
            </div>
            <div className="evidence-cards">
              {answer.evidence
                .filter((e: Obj) => answer.citations.includes(e.id))
                .map((e: Obj) => (
                  <details key={e.id}>
                    <summary>
                      <Badge tone="neutral">{e.id}</Badge>
                      {e.title}
                      <ExternalLink size={13} />
                    </summary>
                    <p>{e.content}</p>
                    {e.source_url.startsWith("https://") && (
                      <a href={e.source_url} target="_blank" rel="noreferrer">
                        打开资料来源 ↗
                      </a>
                    )}
                  </details>
                ))}
            </div>
          </div>
        )}
        <form
          className="ask-box"
          onSubmit={(e) => {
            e.preventDefault();
            ask();
          }}
        >
          <textarea
            aria-label="向证据助手提问"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="问问这个节点的变化，或查看预警背后的依据……"
            rows={2}
          />
          <button
            className="button primary"
            disabled={busy || !question.trim()}
          >
            {busy ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <Send size={17} />
            )}
            发送
          </button>
        </form>
      </Panel>
      <div>
        <Panel title="检索算法链路">
          <div className="rag-steps">
            {[
              ["01", "问题与上下文", "解析节点、指标、事件与时间"],
              ["02", "双路检索", "中文BM25 + 字符TF-IDF"],
              ["03", "融合与去重", "RRF融合排名 + MMR多样性"],
              ["04", "证据增强生成", "结构化实测 + 资料 → DeepSeek"],
              ["05", "引用校验", "校验来源ID，保留检索轨迹"],
            ].map(([n, t, d]) => (
              <div key={n}>
                <span>{n}</span>
                <div>
                  <strong>{t}</strong>
                  <small>{d}</small>
                </div>
              </div>
            ))}
          </div>
          {answer && (
            <details className="retrieval-trace">
              <summary>查看本次实际检索得分</summary>
              <pre>{JSON.stringify(answer.retrieval, null, 2)}</pre>
            </details>
          )}
        </Panel>
        <Panel
          title="知识来源"
          sub={`${knowledge.data?.length || 0} 份来源明确的整理资料`}
        >
          <div className="knowledge-list">
            {knowledge.data?.map((k: Obj) => (
              <div key={k.id}>
                <Layers size={15} />
                <span>{k.title}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function SettingsPage({ cfg, notify, refresh }: Obj) {
  const data = useQuery("/data/status", 4000),
    models = useQuery("/models", 4000);
  const [form, setForm] = useState<Obj>(cfg || {}),
    [job, setJob] = useState<Obj | null>(null);
  useEffect(() => {
    if (cfg) setForm(cfg);
  }, [cfg]);
  const live = job ? null : null;
  useEffect(() => {
    if (!job || ["done", "failed"].includes(job.status)) return;
    const t = setInterval(
      () =>
        api("/jobs/" + job.id).then((j) => {
          setJob(j);
          if (["done", "failed"].includes(j.status)) {
            notify(j.message);
            refresh();
            data.refresh();
            models.refresh();
          }
        }),
      2000,
    );
    return () => clearInterval(t);
  }, [job?.id, job?.status]);
  async function start(kind: string) {
    try {
      const j = await post(
        kind === "import" ? "/data/import" : "/models/train",
        kind === "train" ? { epochs: 12 } : {},
      );
      setJob(j);
      notify("任务已启动，可在本页查看进度");
    } catch (e: any) {
      notify(e.message);
    }
  }
  const model = models.data?.models?.find((m: Obj) => m.status === "active");
  return (
    <>
      <div className="two-columns">
        <Panel
          title="真实公开数据"

          action={
            <Badge tone={data.data?.bounds?.count ? "green" : "neutral"}>
              {data.data?.bounds?.count ? "已导入" : "待导入"}
            </Badge>
          }
        >
          <div className="source-file">
            <Database size={32} />
            <div>
              <strong>Greenhouse-1.xlsx</strong>
              <small>Singh R.K. 等 · LoRaWAN番茄温室 · CC BY 4.0</small>
            </div>
          </div>
          <dl className="evidence-facts">
            <div>
              <dt>温室记录</dt>
              <dd>{data.data?.bounds?.count?.toLocaleString() || 0} 条</dd>
            </div>
            <div>
              <dt>源时间起点</dt>
              <dd>{time(data.data?.bounds?.start)}</dd>
            </div>
            <div>
              <dt>源时间终点</dt>
              <dd>{time(data.data?.bounds?.end)}</dd>
            </div>
            <div>
              <dt>数据字段</dt>
              <dd>T / RH / RSSI / SNR / Date / Time</dd>
            </div>
          </dl>
          <button className="button secondary" onClick={() => start("import")}>
            <RefreshCw size={15} />
            校验并导入数据
          </button>
          <a
            className="source-link"
            target="_blank"
            rel="noreferrer"
            href="https://zenodo.org/records/5793685"
          >
            打开原始发布页 <ExternalLink size={13} />
          </a>
        </Panel>
        <Panel
          title="GRU预测模型"

          action={
            <Badge tone={model ? "green" : "neutral"}>
              {model ? "真实权重已激活" : "尚未训练"}
            </Badge>
          }
        >
          <div className="source-file">
            <ChartNoAxesCombined size={32} />
            <div>
              <strong>共享单层 GRU · hidden 32</strong>
              <small>24×6 输入 → 6×2 输出 · PyTorch / CPU</small>
            </div>
          </div>

          {model && (
            <dl className="evidence-facts">
              <div>
                <dt>训练窗口</dt>
                <dd>{model.metrics.train_windows.toLocaleString()}</dd>
              </div>
              <div>
                <dt>训练 / 验证边界</dt>
                <dd>
                  {model.train_end.slice(0, 10)} / {model.val_end.slice(0, 10)}
                </dd>
              </div>
              <div>
                <dt>真实留出MAE</dt>
                <dd>
                  {model.metrics.temperature_mae} ℃ /{" "}
                  {model.metrics.humidity_mae} %RH
                </dd>
              </div>
            </dl>
          )}
          <button className="button primary" onClick={() => start("train")}>
            <Play size={15} />
            训练并激活 GRU
          </button>
        </Panel>
      </div>
      {job && (
        <div className="glass job-card">
          <div>
            <strong>{job.message}</strong>
            <Badge tone={job.status === "failed" ? "sand" : "green"}>
              {job.status}
            </Badge>
          </div>
          <progress value={job.progress} max="100" />
          <small>
            {val(job.progress, 0)}% ·{" "}
            {job.kind === "train" ? "本地CPU真实训练" : "原始数据读取与校验"}
          </small>
        </div>
      )}
    </>
  );
}

function SensorHistoryPage({ node, setNode, nodes, cursor, onAssistant }: Obj) {
  const [hours, setHours] = useState(8),
    [filter, setFilter] = useState("all");
  const history = useQuery(`/nodes/${node}/series?hours=${hours}`, 6000);
  const selected = nodes.find((n: Obj) => n.id === node);
  const list =
    filter === "all" ? nodes : nodes.filter((n: Obj) => n.state === filter);
  return (
    <>
      <div className="history-toolbar glass">
        <label>
          选择节点
          <select
            aria-label="历史节点选择"
            value={node}
            onChange={(e) => setNode(e.target.value)}
          >
            {nodes.map((n: Obj) => (
              <option key={n.id}>{n.id}</option>
            ))}
          </select>
        </label>
        <label>
          历史范围
          <select
            aria-label="历史时长"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            {[2, 8, 24, 48, 72].map((h) => (
              <option key={h} value={h}>
                过去 {h} 小时
              </option>
            ))}
          </select>
        </label>
        <span>截至源时间 {time(cursor)}</span>
        <button className="button secondary" onClick={() => onAssistant(node)}>
          <Sparkles size={17} />
          解释当前节点
        </button>
      </div>
      <div className="history-summary glass">
        <div>
          <Radio size={22} />
          <strong>{node}</strong>
          <Badge tone={selected?.state === "warning" ? "sand" : "neutral"}>
            {LABELS[selected?.state] || "暂无数据"}
          </Badge>
        </div>
        <span>
          RSSI <b>{val(selected?.rssi, 0)} dBm</b>
        </span>
        <span>
          SNR <b>{val(selected?.snr)} dB</b>
        </span>
        <span>
          观测年龄 <b>{val(selected?.age_seconds / 60, 0)} min</b>
        </span>
      </div>
      <div className="two-columns">
        <Panel title="温度历史变化" sub="实际观测与最多1步前向填补；长缺口留空">
          <Chart
            points={history.data?.points || []}
            metric="temperature"
            height={330}
          />
        </Panel>
        <Panel title="相对湿度历史变化" sub="与温度联合阅读，支持切换历史范围">
          <Chart
            points={history.data?.points || []}
            metric="humidity"
            height={330}
          />
        </Panel>
      </div>
      <div className="two-columns">
        <Panel title="空气VPD变化" sub="由有效T/RH计算的空气环境指标">
          <Chart
            points={history.data?.points || []}
            metric="vpd"
            height={280}
          />
        </Panel>
        <Panel title="无线信号RSSI" sub="真实历史信号强度，不等同真实丢包率">
          <Chart
            points={history.data?.points || []}
            metric="rssi"
            height={280}
          />
        </Panel>
      </div>
      <Panel
        title="节点数据明细"
        sub="点击一行切换当前分析节点"
        action={
          <select
            aria-label="节点状态筛选"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">全部状态</option>
            {["normal", "warning", "stale", "missing", "invalid"].map((v) => (
              <option key={v} value={v}>
                {LABELS[v]}
              </option>
            ))}
          </select>
        }
      >
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {[
                  "节点",
                  "温度 ℃",
                  "湿度 %",
                  "VPD kPa",
                  "RSSI dBm",
                  "SNR dB",
                  "最近源时间",
                  "状态",
                ].map((t) => (
                  <th key={t}>{t}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {list.map((n: Obj) => (
                <tr
                  key={n.id}
                  className={n.id === node ? "selected-row" : ""}
                  onClick={() => setNode(n.id)}
                >
                  <td>{n.id}</td>
                  <td>{val(n.temperature)}</td>
                  <td>{val(n.humidity)}</td>
                  <td>{val(n.vpd, 2)}</td>
                  <td>{val(n.rssi, 0)}</td>
                  <td>{val(n.snr)}</td>
                  <td>{time(n.event_time)}</td>
                  <td>{LABELS[n.state]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

function EnvironmentParameters({ cfg, notify, refresh }: Obj) {
  const [form, setForm] = useState<Obj>(cfg || {});
  useEffect(() => {
    if (cfg) setForm(cfg);
  }, [cfg]);
  return (
    <>
      {" "}
      <Panel
        title="环境参考范围与预警参数"
        sub="以下为教学初始配置，实际使用需结合种植阶段设置"
        action={<Settings2 size={18} />}
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api("/settings", {
                method: "PUT",
                body: JSON.stringify(form),
              });
              notify("配置已保存并重新计算当前提示");
              refresh();
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <div className="settings-fields">
            {[
              ["temperature_min", "温度下限 / ℃"],
              ["temperature_max", "温度上限 / ℃"],
              ["humidity_min", "湿度下限 / %"],
              ["humidity_max", "湿度上限 / %"],
              ["vpd_min", "VPD下限 / kPa"],
              ["vpd_max", "VPD上限 / kPa"],
              ["persistence", "连续有效点数"],
              ["cooldown_minutes", "冷却时长 / min"],
              ["freshness_minutes", "新鲜度时限 / min"],
            ].map(([k, t]) => (
              <label className="form-label" key={k}>
                {t}
                <input
                  type="number"
                  step={
                    k.includes("minutes") || k === "persistence" ? "1" : "0.1"
                  }
                  value={form[k] ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, [k]: Number(e.target.value) })
                  }
                  required
                />
              </label>
            ))}
          </div>
          <button className="button primary">
            <Check size={16} />
            保存配置
          </button>
        </form>
      </Panel>
    </>
  );
}
export default function App() {
  const [user, setUser] = useState<Obj | null>(null),
    [loading, setLoading] = useState(true),
    [username, setUsername] = useState("grower"),
    [password, setPassword] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    api("/auth/me")
      .then((r) => setUser(r.user))
      .finally(() => setLoading(false));
  }, []);
  if (loading)
    return (
      <div className="login-screen">
        <LoaderCircle className="spin" size={32} />
      </div>
    );
  if (user)
    return (
      <Workspace
        user={user}
        onLogout={async () => {
          await post("/auth/logout");
          setUser(null);
        }}
      />
    );
  return (
    <div className="login-screen">
      <div className="photo-backdrop" />
      <form
        className="login-card glass"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setUser(await post("/auth/login", { username, password }));
            setPassword("");
            setError("");
          } catch (e: any) {
            setError(e.message);
          }
        }}
      >
        <div className="login-brand">
          <Leaf size={32} />
          Verdant
        </div>
        <h1>登录温室工作台</h1>
        <div className="login-roles">
          <button
            type="button"
            className={username === "grower" ? "selected" : ""}
            onClick={() => setUsername("grower")}
          >
            温室管理员
          </button>
          <button
            type="button"
            className={username === "operator" ? "selected" : ""}
            onClick={() => setUsername("operator")}
          >
            系统维护员
          </button>
        </div>
        <label className="form-label">
          用户名
          <input
            aria-label="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="form-label">
          密码
          <input
            aria-label="密码"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <div className="notice error">{error}</div>}
        <button className="button primary full">登录</button>
      </form>
    </div>
  );
}
