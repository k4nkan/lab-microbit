export type Step = { id: string; taskId: string; phase: string; taskTitle: string; estimate: string; title: string; body: string; criteria: string[]; hint: string; answer: string; image?: string; answerImage?: string };
export type ArrangeIdea = { id: string; title: string; body: string; hint: string };
export const TASK_VERSION = "2.0.0";
const step = (id: string, taskId: string, phase: string, taskTitle: string, estimate: string, title: string, body: string, criteria: string[], hint: string, answer: string): Step => ({ id, taskId, phase, taskTitle, estimate, title, body, criteria, hint, answer });
const tutorial = (id: string, title: string, body: string, criteria: string[], hint: string, answer: string) => step(id, "tutorial", "チュートリアル", "チュートリアル", "10分", title, body, criteria, hint, answer);
const game = (id: string, title: string, body: string, criteria: string[], hint: string, answer: string) => step(id, "tilt-game", "ゲーム制作", "傾けてゴールを目指すゲーム", "30分", title, body, criteria, hint, answer);

export const steps: Step[] = [
  tutorial("T1", "MakeCodeを準備しよう", "「MakeCodeを開く」からMakeCodeを開き、拡張機能メニューの「Edit Logger」を一度開いてください。ロガーに「記録中」と表示されれば準備完了です。", ["MakeCodeが開いている", "Edit Loggerに「記録中」と表示されている"], "MakeCodeのブロック一覧の下の方に「Edit Logger」があります。開くと自動で記録が始まります。", "Edit Loggerを開き、上部に「実験 P-XXXX に記録中」と表示されていることを確認します。表示されない場合は実験者を呼んでください。"),
  tutorial("T2", "LEDにアイコンを表示しよう", "基本ブロックを使って、LEDに好きなアイコンを表示してください。", ["LEDにアイコンが表示される"], "「基本」カテゴリーから表示に関係するブロックを探します。", "「最初だけ」の中に「アイコンを表示」ブロックを入れ、アイコンを選びます。"),
  tutorial("T3", "ボタンを使おう", "ボタンAを押したとき、表示するアイコンが変わるプログラムを作ってください。", ["ボタンAでアイコンが変わる"], "「入力」カテゴリーにボタン操作のイベントがあります。", "「ボタンAが押されたとき」の中に、別の「アイコンを表示」ブロックを入れます。"),
  tutorial("T4", "動作を確認しよう", "シミュレーターまたは実機でプログラムを動かし、ボタンAを押してください。確認できたら、ここで作ったブロックは消してかまいません。", ["意図した表示に変化することを確認した"], "画面左側のシミュレーターにあるAボタンを押せます。", "シミュレーターのAボタン、または実機のAボタンを押して表示の変化を確認します。"),
  game("G1", "ボールを表示しよう", "変数 x と y を作り、LED画面の真ん中にボールとなる点を1つ表示してください。", ["変数 x と y がある", "LED画面の真ん中に点が表示される"], "「変数」カテゴリーで変数を作れます。LEDの位置は左上が x=0, y=0、右下が x=4, y=4 です。", "「最初だけ」で x と y を 2 にし、「ずっと」の中で「点灯 x x y y」（LEDカテゴリー）を使います。"),
  game("G2", "左右に傾けてボールを動かそう", "micro:bitを右に傾けるとボールが右へ、左に傾けると左へ1マス動くようにしてください。", ["右に傾けると右へ動く", "左に傾けると左へ動く", "前の位置の点が消える"], "「入力」の「ゆさぶられたとき」ブロックは、プルダウンで「右に傾けた」などに変えられます。", "「右に傾けたとき」の中で「表示を消す」→「x を 1 だけ増やす」、「左に傾けたとき」の中で「表示を消す」→「x を -1 だけ増やす」を入れます。"),
  game("G3", "上下にも動かそう", "ロゴを上や下に傾けたとき、ボールが上下に動くようにしてください。", ["上下に傾けるとボールが上下に動く"], "使うのは y です。yは下に行くほど大きくなります。", "「ロゴが上になったとき」で y を 1 増やし、「ロゴが下になったとき」で y を -1 増やします。どちらも先に「表示を消す」を入れます。"),
  game("G4", "ゴールを表示しよう", "ボールとは別の位置にゴールとなる点を表示してください。", ["ゴールの位置が表示される"], "ゴール用に新しい変数を2つ作ります。", "変数 goal_x と goal_y を作り、「最初だけ」で値を決め、「ずっと」の中で「点灯 goal_x goal_y」を追加します。"),
  game("G5", "ゴールしたらハートを出そう", "ボールがゴールに重なったら、ハートのアイコンを表示してください。", ["ゴールに着くとハートが表示される"], "x と goal_x、y と goal_y の両方が等しいかを調べます。「論理」の「かつ」を使います。", "「ずっと」の中に「もし x = goal_x かつ y = goal_y なら」を入れ、その中で「アイコンを表示（ハート）」を使います。"),
  game("G6", "Aボタンでやり直せるようにしよう", "ボタンAを押すと、ボールが最初の位置に戻ってもう一度遊べるようにしてください。", ["ボタンAでボールが真ん中に戻る"], "「最初だけ」で設定した値を、ボタンのイベントの中でもう一度設定します。", "「ボタンAが押されたとき」の中で「表示を消す」、x を 2、y を 2 にします。"),
  game("G7", "実機で遊んでみよう", "完成したゲームをmicro:bitに書き込み、実際に傾けてゴールまで動かしてください。", ["実機でゴールまで動かせた"], "「ダウンロード」ボタンで書き込みます。うまく動かないときはシミュレーターと見比べます。", "USBでmicro:bitをつないで「ダウンロード」を押し、本体を傾けて遊びます。"),
];

export const arrangeIdeas: ArrangeIdea[] = [
  { id: "sound", title: "ゴールしたら音を鳴らす", body: "ハートと一緒にメロディや効果音を鳴らします。", hint: "「音楽」カテゴリーの「メロディを開始する」や「音を鳴らす」を、ゴール判定の「もし」の中に入れます。" },
  { id: "random-goal", title: "ゴールの位置をランダムにする", body: "遊ぶたびにゴールの場所が変わるようにします。", hint: "「計算」の「0から4までの乱数」を goal_x と goal_y に入れます。Aボタンでやり直すときにも同じようにします。" },
  { id: "wall", title: "画面の外に出ないようにする", body: "ボールが端で止まるようにします。", hint: "「もし x < 0 なら x を 0 にする」「もし x > 4 なら x を 4 にする」を、y についても作ります。" },
  { id: "timer", title: "ゴールまでのタイムを表示する", body: "スタートからゴールまでにかかった時間を表示します。", hint: "「入力」の「稼働時間（ミリ秒）」をスタート時に変数へ入れておき、ゴールしたときの差を「数を表示」します。" },
  { id: "score", title: "スコアを数える", body: "ゴールするたびに得点が増え、次のゴールが現れるようにします。", hint: "変数 score を作り、ゴールしたら 1 増やしてゴールの位置を変えます。Bボタンで「数を表示 score」をすると確認できます。" },
  { id: "obstacle", title: "障害物を置く", body: "ぶつかるとゲームオーバーになる点を追加します。", hint: "障害物用の変数を作り、ボールと同じ位置になったら「アイコンを表示（ドクロ）」にします。" },
];
