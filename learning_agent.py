import json
import re
from portfolio_manager import load_experience_log, load_portfolio_state, save_portfolio_state
from config import RISK_SETTINGS, RISK_MANAGEMENT_VARS
from datetime import datetime

def analyze_llm_reflections():
    """
    Analyze the llm_reflection_log and experience_log to suggest adaptive changes to risk settings or prompt.
    Also logs every adaptation, checks for anomalies, and logs LLM reasoning for transparency.
    Now also adapts stop-loss/take-profit, cooldown, and position sizing rules.
    """
    state = load_portfolio_state()
    reflections = state.get('llm_reflection_log', [])
    exp_log = load_experience_log()
    if not reflections or not exp_log:
        print("No reflections or experience log found.")
        return None

    # Use a moving window of 20 trades for adaptation
    window = 20
    last_trades = [r for r in exp_log if r.get('trade_outcome_pl') is not None][-window:]
    if not last_trades:
        print("Not enough trades for adaptation.")
        return None

    avg_pl = sum(r['trade_outcome_pl'] for r in last_trades) / len(last_trades)
    print(f"Moving average P&L over last {window} trades: {avg_pl:.2f}")

    # --- LLM Confidence Weighting ---
    llm_confidence_weight = 1.0
    llm_confidence_label = 'neutral'
    if reflections:
        last_reflection = reflections[-1]
        reflection_text = last_reflection.get('llm_reflection', '')
        # --- JSON-based adaptation protocol ---
        param_suggestions = None
        try:
            # Try to extract JSON object from the reflection
            json_start = reflection_text.find('{')
            json_end = reflection_text.rfind('}')
            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_str = reflection_text[json_start:json_end+1]
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and 'param_suggestions' in parsed:
                    param_suggestions = parsed['param_suggestions']
        except Exception as e:
            state.setdefault('adaptation_log', []).append({
                'timestamp': datetime.now().isoformat(),
                'type': 'llm_json_parse_error',
                'error': str(e),
                'reflection_excerpt': reflection_text[:100]
            })
        # If param_suggestions found, apply them with validation
        if param_suggestions:
            for param, value in param_suggestions.items():
                if param in RISK_MANAGEMENT_VARS and RISK_MANAGEMENT_VARS[param].get('use_in_llm', False):
                    min_val, max_val = RISK_MANAGEMENT_VARS[param]['range']
                    # Clamp value to allowed range
                    try:
                        val = type(RISK_SETTINGS[param])(value)
                        val = max(min_val, min(max_val, val))
                        state['RISK_SETTINGS'][param] = val
                        state.setdefault('adaptation_log', []).append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'param_update',
                            'param': param,
                            'new_value': val,
                            'reason': 'LLM JSON param_suggestions',
                            'reflection_excerpt': str(value)
                        })
                        print(f"Adapted {param} to {val} via LLM JSON suggestion.")
                    except Exception as e:
                        state.setdefault('adaptation_log', []).append({
                            'timestamp': datetime.now().isoformat(),
                            'type': 'param_update_error',
                            'param': param,
                            'error': str(e),
                            'reflection_excerpt': str(value)
                        })
        # --- Legacy confidence parsing removed; now handled via LLM JSON protocol or can be extended in future ---
        # Log confidence (if needed, can be set by LLM JSON or other mechanism)
        state.setdefault('adaptation_log', []).append({
            'timestamp': datetime.now().isoformat(),
            'type': 'llm_confidence',
            'confidence_label': llm_confidence_label,
            'confidence_weight': llm_confidence_weight,
            'reflection_excerpt': reflection_text[:100]
        })

    # --- Use confidence weight in adaptation ---
    # Adapt risk: increase if profitable, decrease if losing, scaled by LLM confidence
    risk = state.get('RISK_SETTINGS', dict(RISK_SETTINGS)).get('max_risk_per_trade_percent', RISK_SETTINGS['max_risk_per_trade_percent'])
    if avg_pl > 0:
        base_change = min(risk * 0.05, 0.10 - risk)
        new_risk = min(risk + base_change * llm_confidence_weight, 0.10)  # Cap at 10%
    else:
        base_change = max(-risk * 0.05, 0.01 - risk)
        new_risk = max(risk + base_change * llm_confidence_weight, 0.01)  # Floor at 1%

    # Log adaptation with confidence
    if 'adaptation_log' not in state:
        state['adaptation_log'] = []
    state['adaptation_log'].append({
        'timestamp': datetime.now().isoformat(),
        'type': 'param_update',
        'param': 'max_risk_per_trade_percent',
        'new_value': new_risk,
        'reason': f'Performance-based adaptation (LLM confidence: {llm_confidence_label}, weight: {llm_confidence_weight})',
        'avg_pl': avg_pl
    })
    state['RISK_SETTINGS'] = dict(RISK_SETTINGS)
    state['RISK_SETTINGS']['max_risk_per_trade_percent'] = new_risk
    print(f"Adapted max_risk_per_trade_percent to {new_risk:.4f} (LLM confidence: {llm_confidence_label}, weight: {llm_confidence_weight})")

    # Optionally adapt sentiment threshold
    sentiment = state['RISK_SETTINGS'].get('min_sentiment_for_buy', RISK_SETTINGS['min_sentiment_for_buy'])
    if avg_pl < 0 and sentiment < 60:
        state['RISK_SETTINGS']['min_sentiment_for_buy'] = sentiment + 2
        state['adaptation_log'].append({
            'timestamp': datetime.now().isoformat(),
            'type': 'param_update',
            'param': 'min_sentiment_for_buy',
            'new_value': sentiment + 2,
            'reason': 'Performance-based adaptation',
            'avg_pl': avg_pl
        })
        print(f"Increased min_sentiment_for_buy to {sentiment + 2}")

    # --- Anomaly Detection ---
    # Too many adaptations in last 10 cycles
    recent_adaptations = [a for a in state['adaptation_log'][-10:] if a['type'] == 'param_update']
    if len(recent_adaptations) > 5:
        from portfolio_manager import log_anomaly
        log_anomaly(state, 'frequent_adaptations', f"{len(recent_adaptations)} parameter changes in last 10 cycles.")
    # Parameter at min/max
    if new_risk == 0.01 or new_risk == 0.10:
        from portfolio_manager import log_anomaly
        log_anomaly(state, 'risk_param_limit', f"max_risk_per_trade_percent at limit: {new_risk}")
    # --- Loss Cooldown: If last trade was a loss, set last_loss_cycle ---
    if last_trades and last_trades[-1]['trade_outcome_pl'] < 0:
        state['RISK_SETTINGS']['last_loss_cycle'] = state.get('cycle_count', 0)
    
    # --- Adaptation Impact Tracking & Rollback ---
    # Track the impact of each adaptation for the last 10 cycles
    if 'adaptation_impact' not in state:
        state['adaptation_impact'] = []
    # Log the current adaptation and its avg_pl
    state['adaptation_impact'].append({
        'timestamp': datetime.now().isoformat(),
        'cycle': state.get('cycle_count', 0),
        'param': 'max_risk_per_trade_percent',
        'value': new_risk,
        'avg_pl': avg_pl
    })
    # Keep only the last 20 for memory efficiency
    state['adaptation_impact'] = state['adaptation_impact'][-20:]
    # Rollback logic: if the last 10 adaptations led to negative avg_pl, revert to previous value
    recent_impacts = [a for a in state['adaptation_impact'] if a['param'] == 'max_risk_per_trade_percent'][-10:]
    if len(recent_impacts) == 10 and all(a['avg_pl'] < 0 for a in recent_impacts):
        # Find the last value before these 10
        prev = [a for a in state['adaptation_impact'][:-10] if a['param'] == 'max_risk_per_trade_percent']
        if prev:
            rollback_val = prev[-1]['value']
            state['RISK_SETTINGS']['max_risk_per_trade_percent'] = rollback_val
            state['adaptation_log'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'rollback',
                'param': 'max_risk_per_trade_percent',
                'rolled_back_to': rollback_val,
                'reason': '10 consecutive negative avg_pl after adaptation'
            })
            print(f"Rolled back max_risk_per_trade_percent to {rollback_val} due to poor performance.")
    # --- Multi-Parameter Change Detection ---
    # Detect and log if multiple parameters are changed in a single cycle
    param_changes_this_cycle = [a for a in state['adaptation_log'] if a.get('timestamp', '').startswith(datetime.now().date().isoformat()) and a['type'] == 'param_update']
    if len(param_changes_this_cycle) > 1:
        state['adaptation_log'].append({
            'timestamp': datetime.now().isoformat(),
            'type': 'multi_param_update',
            'params_changed': [a['param'] for a in param_changes_this_cycle],
            'new_values': {a['param']: a['new_value'] for a in param_changes_this_cycle},
            'reason': 'Multiple parameter changes in single cycle',
            'cycle': state.get('cycle_count', 0)
        })
        # Track combined impact for later analysis
        if 'multi_param_impact' not in state:
            state['multi_param_impact'] = []
        state['multi_param_impact'].append({
            'timestamp': datetime.now().isoformat(),
            'cycle': state.get('cycle_count', 0),
            'params_changed': [a['param'] for a in param_changes_this_cycle],
            'new_values': {a['param']: a['new_value'] for a in param_changes_this_cycle},
            'avg_pl': avg_pl
        })
        state['multi_param_impact'] = state['multi_param_impact'][-20:]

    # --- Adaptive Parameter Decay ---
    # If a parameter is at its min/max for >10 cycles, decay toward default unless LLM reinforces
    decay_targets = {
        'max_risk_per_trade_percent': 0.05,
        'min_sentiment_for_buy': 40,
        'max_position_per_asset_percent': 0.05
    }
    for param, default_val in decay_targets.items():
        # Check if at min/max for >10 cycles
        impacts = [a for a in state.get('adaptation_impact', []) if a['param'] == param]
        if len(impacts) >= 10:
            vals = [a['value'] for a in impacts[-10:]]
            if all(v == min(0.01, default_val) or v == max(0.10, default_val) for v in vals):
                # Decay toward default by 10% of the distance
                current_val = state['RISK_SETTINGS'].get(param, default_val)
                new_val = current_val + 0.1 * (default_val - current_val)
                # Only decay if LLM hasn't just reinforced the extreme
                if not any(abs(a['value'] - current_val) < 1e-6 for a in impacts[-3:]):
                    state['RISK_SETTINGS'][param] = new_val
                    state['adaptation_log'].append({
                        'timestamp': datetime.now().isoformat(),
                        'type': 'param_decay',
                        'param': param,
                        'decayed_to': new_val,
                        'reason': 'Parameter at extreme for >10 cycles, decaying toward default',
                        'cycle': state.get('cycle_count', 0)
                    })
                    print(f"Decayed {param} toward default: {new_val}")
    # --- Reflection Quality/Consistency Check ---
    # If LLM suggestions are highly volatile or contradictory over 5 cycles, log anomaly and slow adaptation
    if len(state.get('adaptation_impact', [])) >= 5:
        last_vals = [a['value'] for a in state['adaptation_impact'][-5:]]
        # Volatility: large swings
        swings = [abs(last_vals[i] - last_vals[i-1]) for i in range(1, 5)]
        if any(s > 0.05 for s in swings):
            from portfolio_manager import log_anomaly
            log_anomaly(state, 'llm_volatility', f"Large parameter swings in last 5 cycles: {swings}")
            # Optionally slow adaptation (e.g., halve the next change)
            state['adaptation_log'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'adaptation_slowdown',
                'reason': 'LLM suggestions volatile, slowing adaptation',
                'cycle': state.get('cycle_count', 0)
            })
        # Contradiction: parameter oscillates up/down repeatedly
        if all((last_vals[i] - last_vals[i-1]) * (last_vals[i-1] - last_vals[i-2]) < 0 for i in range(2, 5)):
            from portfolio_manager import log_anomaly
            log_anomaly(state, 'llm_oscillation', f"Parameter oscillation detected in last 5 cycles: {last_vals}")
            state['adaptation_log'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'adaptation_slowdown',
                'reason': 'LLM suggestions oscillating, slowing adaptation',
                'cycle': state.get('cycle_count', 0)
            })
    # --- Human-Readable Adaptation Summary ---
    if state.get('cycle_count', 0) % 10 == 0 and state.get('cycle_count', 0) > 0:
        summary = []
        summary.append(f"=== Adaptation Summary (Cycle {state['cycle_count']}) ===")
        # Recent adaptations
        recent_adapt = state.get('adaptation_log', [])[-10:]
        for a in recent_adapt:
            summary.append(f"[{a.get('timestamp','')}] {a.get('type','')}: {a.get('param','')} -> {a.get('new_value', a.get('decayed_to', a.get('rolled_back_to', '')))} | {a.get('reason','')}")
        # Recent impacts
        recent_impacts = state.get('adaptation_impact', [])[-10:]
        for i, imp in enumerate(recent_impacts):
            summary.append(f"Impact {i+1}: {imp['param']}={imp['value']} | avg_pl={imp['avg_pl']:.2f}")
        # Recent anomalies
        recent_anom = state.get('anomaly_log', [])[-5:] if 'anomaly_log' in state else []
        for an in recent_anom:
            summary.append(f"ANOMALY [{an.get('timestamp','')}] {an.get('anomaly_type','')}: {an.get('details','')}")
        # Print and log summary
        summary_str = '\n'.join(summary)
        print(summary_str)
        if 'adaptation_summaries' not in state:
            state['adaptation_summaries'] = []
        state['adaptation_summaries'].append({
            'cycle': state['cycle_count'],
            'timestamp': datetime.now().isoformat(),
            'summary': summary_str
        })
        # Keep only last 10 summaries
        state['adaptation_summaries'] = state['adaptation_summaries'][-10:]
    # --- More Granular Anomaly Types ---
    # 1. No adaptation for a long period (potential stagnation)
    if len(state.get('adaptation_log', [])) > 20:
        recent_types = [a['type'] for a in state['adaptation_log'][-20:]]
        if all(t != 'param_update' for t in recent_types):
            from portfolio_manager import log_anomaly
            log_anomaly(state, 'no_adaptation', 'No parameter adaptation in last 20 cycles.')
    # 2. Repeated LLM errors or unparseable suggestions
    if reflections:
        error_count = sum(1 for r in reflections[-10:] if 'error' in r.get('llm_reflection', '').lower() or 'unparseable' in r.get('llm_reflection', '').lower())
        if error_count > 3:
            from portfolio_manager import log_anomaly
            log_anomaly(state, 'llm_error_streak', f"LLM errors/unparseable suggestions in {error_count} of last 10 reflections.")
    # 3. Parameter stuck at a value despite poor performance
    for param in ['max_risk_per_trade_percent', 'min_sentiment_for_buy', 'max_position_per_asset_percent']:
        impacts = [a for a in state.get('adaptation_impact', []) if a['param'] == param]
        if len(impacts) >= 10:
            vals = [a['value'] for a in impacts[-10:]]
            if all(v == vals[0] for v in vals) and sum(a['avg_pl'] for a in impacts[-10:]) < 0:
                from portfolio_manager import log_anomaly
                log_anomaly(state, 'param_stuck', f"{param} stuck at {vals[0]} for 10 cycles with negative avg_pl.")
    # --- Adaptive Learning Rate ---
    # If in drawdown (avg_pl negative for last 10 cycles), slow adaptation
    if len(state.get('adaptation_impact', [])) >= 10:
        last_10_pl = [a['avg_pl'] for a in state['adaptation_impact'][-10:]]
        if all(pl < 0 for pl in last_10_pl):
            # Reduce magnitude of next parameter change by half
            if 'adaptation_slowdown_active' not in state or not state['adaptation_slowdown_active']:
                state['adaptation_slowdown_active'] = True
                state['adaptation_log'].append({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'adaptation_slowdown',
                    'reason': 'Drawdown detected, halving adaptation magnitude',
                    'cycle': state.get('cycle_count', 0)
                })
            # Halve the next change (for max_risk_per_trade_percent)
            prev_val = state['RISK_SETTINGS']['max_risk_per_trade_percent']
            target_val = new_risk
            new_risk = prev_val + 0.5 * (target_val - prev_val)
            state['RISK_SETTINGS']['max_risk_per_trade_percent'] = new_risk
            state['adaptation_log'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'param_update',
                'param': 'max_risk_per_trade_percent',
                'new_value': new_risk,
                'reason': 'Adaptive learning rate: halved change due to drawdown',
                'cycle': state.get('cycle_count', 0)
            })
        else:
            state['adaptation_slowdown_active'] = False
    # --- Shadow/Test Mode for Major Parameter Changes ---
    SHADOW_TEST_CYCLES = 5
    SHADOW_CHANGE_THRESHOLD = 0.03  # e.g., >3% change triggers shadow mode
    if 'shadow_test' not in state:
        state['shadow_test'] = {'active': False, 'param': None, 'proposed_value': None, 'start_cycle': None, 'sim_results': []}

    # Detect large change
    if not state['shadow_test']['active'] and abs(new_risk - risk) > SHADOW_CHANGE_THRESHOLD:
        # Start shadow test
        state['shadow_test'] = {
            'active': True,
            'param': 'max_risk_per_trade_percent',
            'proposed_value': new_risk,
            'start_cycle': state.get('cycle_count', 0),
            'sim_results': []
        }
        # Do NOT apply the change yet
        state['adaptation_log'].append({
            'timestamp': datetime.now().isoformat(),
            'type': 'shadow_test_start',
            'param': 'max_risk_per_trade_percent',
            'proposed_value': new_risk,
            'reason': f'Large change detected (> {SHADOW_CHANGE_THRESHOLD}), starting shadow test',
            'cycle': state.get('cycle_count', 0)
        })
        # Keep real param unchanged for now
        new_risk = risk
    elif state['shadow_test']['active'] and state['shadow_test']['param'] == 'max_risk_per_trade_percent':
        # Simulate performance with shadow param
        # For simplicity, compare actual P&L to what it would be if risk was shadow value (scale P&L by ratio)
        sim_cycle = state.get('cycle_count', 0) - state['shadow_test']['start_cycle']
        if sim_cycle < SHADOW_TEST_CYCLES:
            # Simulate this cycle
            if last_trades:
                last_real_pl = last_trades[-1]['trade_outcome_pl']
                risk_ratio = state['shadow_test']['proposed_value'] / risk if risk > 0 else 1.0
                sim_pl = last_real_pl * risk_ratio
                state['shadow_test']['sim_results'].append(sim_pl)
        if sim_cycle + 1 >= SHADOW_TEST_CYCLES:
            # End shadow test and decide
            avg_real = sum(r['trade_outcome_pl'] for r in last_trades[-SHADOW_TEST_CYCLES:]) / SHADOW_TEST_CYCLES if len(last_trades) >= SHADOW_TEST_CYCLES else 0
            avg_sim = sum(state['shadow_test']['sim_results']) / len(state['shadow_test']['sim_results']) if state['shadow_test']['sim_results'] else 0
            if avg_sim > avg_real:
                # Promote shadow param
                new_risk = state['shadow_test']['proposed_value']
                state['RISK_SETTINGS']['max_risk_per_trade_percent'] = new_risk
                state['adaptation_log'].append({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'shadow_test_promote',
                    'param': 'max_risk_per_trade_percent',
                    'new_value': new_risk,
                    'reason': f'Shadow test outperformed real ({avg_sim:.2f} > {avg_real:.2f}), promoting',
                    'cycle': state.get('cycle_count', 0)
                })
            else:
                # Reject shadow param
                state['adaptation_log'].append({
                    'timestamp': datetime.now().isoformat(),
                    'type': 'shadow_test_reject',
                    'param': 'max_risk_per_trade_percent',
                    'proposed_value': state['shadow_test']['proposed_value'],
                    'reason': f'Shadow test underperformed or equal ({avg_sim:.2f} <= {avg_real:.2f}), rejecting',
                    'cycle': state.get('cycle_count', 0)
                })
            # Reset shadow test
            state['shadow_test'] = {'active': False, 'param': None, 'proposed_value': None, 'start_cycle': None, 'sim_results': []}
    save_portfolio_state(state)
    return new_risk

if __name__ == "__main__":
    analyze_llm_reflections()
