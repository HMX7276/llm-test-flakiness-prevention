"""Export descriptive counts; intentionally no unsupported inferential error bars."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ['MPLCONFIGDIR'] = str(ROOT / 'runs/figure_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    source = ROOT / 'analysis/lean_followup_v1_summary.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    assert data['primary_execution_complete'] and data['diagnostic_quality_complete'], 'Do not plot pending outcomes as zeros.'
    models = ['qwen3.5', 'deepseek-v4-flash']
    methods = ['B0', 'B1', 'B2', 'M']
    groups = {(g['model'], g['method']): g for g in data['groups']}
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.4), sharey=True)
    for ax, model in zip(axes, models):
        upper = [groups[(model, method)]['stable_proxy_valid'] for method in methods]
        lower = [groups[(model, method)]['stable_and_detects_any_diagnostic_defect'] for method in methods]
        assert all(a <= b <= 9 for a, b in zip(lower, upper))
        ax.bar(methods, upper, color='#bdd7e7', edgecolor='#416b85', linewidth=0.8,
               label='Stable proxy-valid', width=0.62)
        ax.bar(methods, lower, color='#205a7a', width=0.62,
               label='Also detects a diagnostic defect')
        for x, hi, lo in zip(range(4), upper, lower):
            ax.text(x, hi + 0.15, str(hi), ha='center', fontsize=10)
            if lo:
                ax.text(x, lo / 2, str(lo), ha='center', va='center', color='white', fontsize=10)
        ax.set_title(model, fontsize=11)
        ax.set_ylim(0, 10)
        ax.set_yticks(range(0, 10))
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=0.18)
        ax.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Generated outputs (9 scheduled per model/method)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(0.5, 0.88), ncol=2, frameon=False, fontsize=9)
    fig.suptitle('Controlled follow-up on three previously seen targets', fontsize=12, y=0.99)
    fig.text(0.5, 0.035, 'B0: original example   B1: warning   B2: example omitted   M: preprocessing\n'
             'Primary protocol only; gate sensitivity changes the comparison.',
             ha='center', fontsize=8)
    fig.subplots_adjust(top=0.70, bottom=0.22, left=0.08, right=0.98, wspace=0.17)
    dest = ROOT / 'paper/figures'
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in ['png', 'svg']:
        fig.savefig(dest / ('lean_followup_v1_counts.' + suffix), dpi=200)
    plt.close(fig)
    (dest / 'lean_followup_v1_counts_provenance.json').write_text(json.dumps({
        'source': source.relative_to(ROOT).as_posix(), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'scope': data['scope'], 'denominator': '9 scheduled cells per model/method; 3 targets x 3 generations',
        'meaning': 'Dark bars are a subset of light bars, not an added count. Diagnostic defect detection requires 3/3 failures with target calls.',
        'uncertainty': 'Descriptive counts only; no significance, equivalence, or semantic validity claim.'}, indent=2) + '\n', encoding='utf-8')
    print('Exported PNG and SVG with source-hash provenance; descriptive counts only.')


if __name__ == '__main__':
    main()
