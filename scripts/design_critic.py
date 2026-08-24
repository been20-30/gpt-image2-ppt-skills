#!/usr/bin/env python3
"""Actionable design critic: diagnostics become repair/regeneration instructions."""
from __future__ import annotations

def critic_from_design(result):
    repairs=[]
    for finding in result.get('findings',[]):
        code=finding.get('code'); slide=finding.get('slide')
        if code=='repeated_layout':
            repairs.append({'slide':slide,'problem':'Card or composition repetition detected','cause':'Adjacent slides share the same composition family or signature.','recommended_change':'Replace the repeated family with a distinct visual framework or editorial composition.','regeneration_instruction':'select_layout(framework_or_editorial); regenerate with a new focal structure and no adjacent reuse.'})
        elif code=='card_overuse':
            repairs.append({'slide':slide,'problem':'Card overuse detected','cause':'The deck relies on modular cards instead of a visual argument.','recommended_change':'Replace cards with a diagram, timeline, comparison, or single visual metaphor.','regeneration_instruction':'select_layout(diagram_or_timeline); regenerate without default card containers.'})
        elif code=='text_over_budget':
            repairs.append({'slide':slide,'problem':'Typography budget exceeded','cause':'Too much copy for the selected density and text zone.','recommended_change':'Reduce to one insight and up to three supporting points, or split the slide.','regeneration_instruction':'regenerate with sparse copy, larger Arabic type, and the protected safe zone.'})
        elif code=='unknown_family':
            repairs.append({'slide':slide,'problem':'Undefined art direction family','cause':'The slide has no recognized visual strategy.','recommended_change':'Choose a taxonomy family based on story role.','regeneration_instruction':'select_layout(framework|process|comparison|editorial); regenerate.'})
    if not repairs and result.get('score',0)<80:
        repairs.append({'slide':None,'problem':'Premium design threshold not met','cause':'The aggregate design score is below the acceptance floor.','recommended_change':'Re-plan the weakest scored dimension before generating again.','regeneration_instruction':'re-run Presentation Intelligence with a new art direction and composition sequence.'})
    return {'engine':'design_critic','repairs':repairs,'repair_count':len(repairs),'next_action':'regenerate' if repairs else 'accept'}
