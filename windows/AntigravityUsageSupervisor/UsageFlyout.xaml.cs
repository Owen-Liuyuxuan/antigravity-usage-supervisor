using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Input;
using TextBlock = System.Windows.Controls.TextBlock;
using ProgressBar = System.Windows.Controls.ProgressBar;
using Color = System.Windows.Media.Color;

namespace AntigravityUsageSupervisor;

public partial class UsageFlyout : Window
{
    public UsageFlyout()
    {
        InitializeComponent();
        Deactivated += (_, _) => Hide();
        KeyDown += (_, e) => { if (e.Key == Key.Escape) Hide(); };
        Closing += (_, e) => { e.Cancel = true; Hide(); };
    }

    public void Reveal()
    {
        Show();
        var area = System.Windows.Forms.Screen.FromPoint(System.Windows.Forms.Cursor.Position).WorkingArea;
        var source = PresentationSource.FromVisual(this);
        var transform = source?.CompositionTarget?.TransformFromDevice ?? Matrix.Identity;
        var corner = transform.Transform(new System.Windows.Point(area.Right, area.Bottom));
        var origin = transform.Transform(new System.Windows.Point(area.Left, area.Top));
        Height = Math.Min(720, corner.Y - origin.Y - 20);
        Left = Math.Max(origin.X + 10, corner.X - Width - 12);
        Top = Math.Max(origin.Y + 10, corner.Y - Height - 12);
        Activate();
    }

    internal static double? Percent(JsonNode? window) => window?["used_percent"]?.GetValue<double>();
    internal static string Compact(double value) => value >= 1_000_000 ? $"{value / 1_000_000:0.##}M" : value >= 1000 ? $"{value / 1000:0.#}K" : $"{value:0}";
    private static readonly (string Key, string Label)[] QuotaRows =
    [
        ("gemini_5h", "Gemini · 5 小时"),
        ("gemini_weekly", "Gemini · 每周"),
        ("claude_gpt_5h", "Claude 和 GPT · 5 小时"),
        ("claude_gpt_weekly", "Claude 和 GPT · 每周"),
    ];

    private static readonly SolidColorBrush Muted = new(Color.FromRgb(98, 125, 140));

    private static string ResetText(JsonNode data)
    {
        if (!DateTimeOffset.TryParse(data["resets_at"]?.ToString(), out var timestamp))
            return "重置时间未知";
        var remaining = timestamp - DateTimeOffset.Now;
        return remaining.TotalSeconds <= 0
            ? "重置时间已过，等待更新"
            : $"{timestamp.ToLocalTime():MM/dd HH:mm} 重置 · 剩余 {(int)remaining.TotalHours}小时 {remaining.Minutes}分";
    }

    private void AddQuota(string label, JsonNode? data)
    {
        if (data == null || Percent(data) is not double percent) return;
        var header = new DockPanel();
        var value = new TextBlock { Text = $"{percent:0.##}%", FontSize = 19 };
        DockPanel.SetDock(value, Dock.Right);
        header.Children.Add(value);
        header.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center });
        Quotas.Children.Add(header);
        Quotas.Children.Add(new ProgressBar
        {
            Height = 5, Margin = new Thickness(0, 5, 0, 4), Maximum = 100,
            Value = Math.Clamp(percent, 0, 100), BorderThickness = new Thickness(0),
            Background = new SolidColorBrush(Color.FromRgb(220, 238, 245)),
            Foreground = new SolidColorBrush(percent >= 90 ? Color.FromRgb(201, 63, 68)
                : percent >= 70 ? Color.FromRgb(180, 119, 20) : Color.FromRgb(38, 157, 199))
        });
        Quotas.Children.Add(new TextBlock { Text = ResetText(data), Foreground = Muted, FontSize = 11, Margin = new Thickness(0, 0, 0, 9) });
    }

    internal static (string Label, double? Percent) TrayQuota(JsonNode? limits)
    {
        var gemini5h = Percent(limits?["gemini_5h"]);
        var geminiWeekly = Percent(limits?["gemini_weekly"]);
        if (gemini5h is double g5 && geminiWeekly is double gw)
            return gw > g5 ? ("Gemini · 每周", gw) : ("Gemini · 5 小时", g5);
        foreach (var (key, label) in QuotaRows)
            if (Percent(limits?[key]) is double percent) return (label, percent);
        return ("账户", Percent(limits?["primary"]) ?? Percent(limits?["secondary"]));
    }

    internal void Update(JsonNode snapshot)
    {
        var limits = snapshot["rate_limits"];
        Quotas.Children.Clear();
        foreach (var (key, label) in QuotaRows) AddQuota(label, limits?[key]);
        if (Quotas.Children.Count == 0)
        {
            AddQuota("当前额度", limits?["primary"]);
            AddQuota("另一额度窗口", limits?["secondary"]);
        }
        if (Quotas.Children.Count == 0)
            Quotas.Children.Add(new TextBlock { Text = "暂无账户额度", Foreground = Muted });
        var today = snapshot["today"]!;
        var minutes = today["focus_minutes"]!.GetValue<int>();
        Today.Text = $"{minutes / 60}h {minutes % 60}m   ·   {today["sessions"]} 任务   ·   {Compact(today["tokens"]!.GetValue<double>())} tokens";
        Recent.Children.Clear();
        foreach (var item in snapshot["recent"]!.AsArray())
        {
            Recent.Children.Add(new TextBlock { Text = item!["name"]!.ToString(), TextTrimming = TextTrimming.CharacterEllipsis, TextWrapping = TextWrapping.NoWrap, Margin = new Thickness(0, 7, 0, 3) });
            Recent.Children.Add(new TextBlock { Text = $"{item["project"]} · {Compact(item["tokens"]!.GetValue<double>())} tokens", Foreground = new SolidColorBrush(Color.FromRgb(98, 125, 140)), FontSize = 11 });
        }
        if (Recent.Children.Count == 0) Recent.Children.Add(new TextBlock { Text = "暂无本地任务", Margin = new Thickness(0, 10, 0, 0) });
        var fresh = snapshot["rate_limits_source"]?.ToString() == "cloudcode-api";
        var observed = DateTimeOffset.TryParse(limits?["observed_at"]?.ToString(), out var stamp) ? stamp.ToLocalTime().ToString("MM/dd HH:mm") : "未知";
        var error = snapshot["rate_limits_refresh_error"]?.ToString();
        Status.Text = fresh ? $"账户实时查询 · {limits?["plan_type"]} · {DateTime.Now:HH:mm:ss} 更新"
            : limits != null ? $"本地快照（{observed}）· 实时额度暂不可用"
            : error?.StartsWith("Open agy and sign in", StringComparison.Ordinal) == true
                ? "请从托盘菜单打开 agy 登录 Google，完成后刷新。"
                : "实时额度暂不可用 · 本机活动仍会更新";
        Status.ToolTip = error;
    }

    private async void RefreshClick(object sender, RoutedEventArgs e) => await ((App)System.Windows.Application.Current).Refresh();
    private async void SettingsClick(object sender, RoutedEventArgs e) => await ((App)System.Windows.Application.Current).ShowSettings();
    private void HideClick(object sender, RoutedEventArgs e) => Hide();
}
