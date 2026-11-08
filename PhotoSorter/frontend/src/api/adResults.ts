import {api,query} from './client'
import type {DetectedScreen} from './screenSearch'

const base=(run:string)=>'/ad-results/runs/'+encodeURIComponent(run)
const recognition=(run:string)=>'/ad-recognition/runs/'+encodeURIComponent(run)

export type AdResultStatus='completed'|'not_processed'|'processing'|'queued'|'failed'|'pending'
export type AdClassification='confirmed'|'probable'|'unidentified'
export type ResultScreen=Omit<Partial<DetectedScreen>,'status'>&{
 screen_id:string;screen_name?:string;status:string;reason?:string;crop_url?:string
}
export interface XfeatPhoto {
 index:number;assigned_sam?:string|null;group_id?:string|null;image_url:string
 status:string;reason?:string;image_width?:number;image_height?:number
 model_signature?:string;screens:ResultScreen[]
}
export interface SourcePage<T> {status:AdResultStatus;photos:T[];next_cursor:string|null}

export interface VisualPeer{index:number;screen_id:string;similarity:number}
export interface VisualMember{
 index:number;screen_id:string;assigned_sam:string;screen_name?:string
 annotation_id?:string;embedding_file?:string
 joined_via?:VisualPeer|null;nearest_peers?:VisualPeer[];nearest_separate?:VisualPeer|null
}
export interface GroupMatch {
 group_id:string;status:string;reason:string;candidate_id:string|null
 best_score?:number|null;margin:number|null;matching_threshold:number
 candidate_count:number;method:string;decision_version?:string
 ocr_leader_id?:string|null;visual_leader_id?:string|null
 ocr_margin?:number|null;ocr_conflicting_members?:boolean
 matched_member_count?:number;unmatched_member_count?:number;member_layout_count?:number
}
export interface VisualGroup {
 id:string;assigned_sam:string;screen_id:string;member_count:number
 threshold:number;formation_reason?:string;separation_reason?:string
 min_pairwise_similarity:number|null;mean_pairwise_similarity:number|null
 nearest_other_group?:string|null;nearest_other_similarity?:number|null
 preview?:{index:number;screen_id:string};members?:VisualMember[]
 match?:GroupMatch|{status:string;reason?:string}
}
export interface VisualGroupsPage{
 status:AdResultStatus;match_status?:string;run_id?:string
 grouping_threshold?:number;screen_count?:number;embedded_count?:number
 total:number;limit?:number;offset?:number;groups:VisualGroup[]
 errors?:{index:number;screen_id:string;reason:string}[]
}
export interface RankedLayout {
 id:string;name:string;score:number;version:number;checksum:string
 minimum_member_score?:number;maximum_member_score?:number;member_score?:number
 ocr_matched_terms?:number;ocr_total_terms?:number;ocr_similarity?:number
 ocr_support?:number;relative_dino?:number;combined_score?:number
}
export interface MemberLayoutDecision {
 index:number;screen_id:string;status:string;candidate_id:string|null
 reason:string;best_score?:number|null;method?:string;ocr_leader_id?:string|null
 visual_leader_id?:string|null;ocr_margin?:number|null
}
export interface RankingsPage {
 status:string;group_id:string;reason?:string;candidate_id?:string|null
 best_score?:number|null;margin?:number|null;member_margin?:number|null
 matching_threshold?:number;method?:string;selected_member?:{index:number;screen_id:string}|null
 decision_version?:string;ocr_leader_id?:string|null;visual_leader_id?:string|null
 ocr_margin?:number|null;ocr_conflicting_members?:boolean
 matched_member_count?:number;unmatched_member_count?:number;member_layout_count?:number
 member_decision?:MemberLayoutDecision|null
 total:number;limit?:number;offset?:number;rankings:RankedLayout[]
}
export interface TextSubgroup {
 id:string;visual_group_id:string;assigned_sam:string;screen_id:string
 candidate_id:string|null;status:AdClassification;member_count:number
 text:string;reason:string;significant?:Record<string,string[]>
 members?:{index:number;screen_id:string;classification:string;review_required:boolean;
           normalized_text:string;confidence:number;ocr_status?:string}[]
}
export interface TextSubgroupsPage{
 status:AdResultStatus;subgroup_count?:number;visual_group_count?:number
 confirmed?:number;probable?:number;unidentified?:number
 total:number;limit?:number;offset?:number;subgroups:TextSubgroup[]
}
export interface AdvertisingLayout {
 id:string;name:string;version?:number|null;checksum?:string
 prepared_text:string;image_url:string|null
 photos:number;subgroups:number;confirmed:number;probable:number;unidentified:number
 constructions:string[]
}
export interface AdvertisingLayoutsPage{
 status:AdResultStatus;run_id?:string;total:number;limit?:number;offset?:number
 layouts:AdvertisingLayout[];grouping_threshold?:number
 matching_threshold?:number;layout_library_revision?:number
}
export interface PhotoQuality{
 status:string;score:number;version?:string
 metrics?:Record<string,number>
}
export interface AdPhoto {
 index:number;screen_id:string;image_url:string;crop_url:string
 assigned_sam:string;visual_group_id:string;text_subgroup_id:string
 text_subgroup_status:string;classification:string;quality?:PhotoQuality
 review_required:boolean;best:boolean;ocr_status?:string;ocr_reason?:string
 ocr_matched_terms?:number;ocr_total_terms?:number
 ocr_selection_score?:number;selection_score?:number
}
export interface AdPhotosPage {
 status:AdResultStatus;total:number;limit?:number;offset?:number
 layout_id?:string;subgroup_id?:string|null;best_only?:boolean;photos:AdPhoto[]
}
export interface OcrLine {text:string;score:number;polygon?:number[][]}
export interface OcrObservation {
 status:string;confidence:number;normalized_text:string
 raw_lines:OcrLine[];regions:OcrLine[];significant:Record<string,string[]>
 reason?:string
}
export interface OcrEvidence {
 status:string;reason?:string;matched_terms?:number;total_terms?:number
 text_similarity?:number;matched_items?:string[];unmatched_items?:string[]
 comparison_confidence?:number;scoring_basis?:string
 ambiguous_candidates?:string[];possible_contradictions?:{kind:string;expected:string[];observed:string[]}[]
 contradictions?:{kind:string;expected:string[];observed:string[]}[]
 expected_text?:string;lines?:string[]
}
export interface OcrRecognition {
 status:string;reason?:string;candidate_id?:string|null;layout_name?:string|null
 layout_text?:string|null;classification?:AdClassification;review_required?:boolean
 visual_group_id?:string;text_subgroup_id?:string
 ocr:OcrEvidence;observation?:OcrObservation;quality?:PhotoQuality
}
export interface OcrScreen extends ResultScreen {recognition?:OcrRecognition}
export interface OcrPhoto extends XfeatPhoto {screens:OcrScreen[]}

export const adResultsApi={
 screens:(run:string,cursor?:string|null,limit=24)=>
  api<SourcePage<XfeatPhoto>>(base(run)+'/screens'+query({cursor,limit})),
 visualGroups:(run:string,limit=50,offset=0)=>
  api<VisualGroupsPage>(recognition(run)+'/visual-groups'+query({limit,offset})),
 visualGroup:(run:string,group:string)=>
  api<VisualGroup>(recognition(run)+'/visual-groups/'+encodeURIComponent(group)),
 rankings:(run:string,group:string,options:{
    limit?:number;offset?:number;index?:number;screen_id?:string
  }={})=>
  api<RankingsPage>(recognition(run)+'/visual-groups/'+encodeURIComponent(group)+'/rankings'+query(options)),
 layoutMemberScores:(run:string,group:string,layout:string,limit=50,offset=0)=>
  api<{status:string;total:number;scores:VisualPeer[]}>(recognition(run)+
    '/visual-groups/'+encodeURIComponent(group)+'/layouts/'+encodeURIComponent(layout)+'/members'+query({limit,offset})),
 textGroups:(run:string,options:{limit?:number;offset?:number;visual_group_id?:string;layout_id?:string}={})=>
  api<TextSubgroupsPage>(recognition(run)+'/text-subgroups'+query(options)),
 textGroup:(run:string,subgroup:string)=>
  api<TextSubgroup>(recognition(run)+'/text-subgroups/'+encodeURIComponent(subgroup)),
 recognition:(run:string,index:number,screenId:string)=>
  api<OcrRecognition>(recognition(run)+'/photos/'+index+'/screens/'+encodeURIComponent(screenId)),
 layouts:(run:string,limit=50,offset=0)=>
  api<AdvertisingLayoutsPage>(base(run)+'/layouts'+query({limit,offset})),
 layoutImage:(run:string,layout:string)=>
  '/api'+base(run)+'/layouts/'+encodeURIComponent(layout)+'/image',
 photos:(run:string,layout:string,options:{
    subgroup_id?:string;best_only?:boolean;limit?:number;offset?:number
  }={})=>api<AdPhotosPage>(base(run)+'/layouts/'+encodeURIComponent(layout)+'/photos'+query(options)),
 ocr:(run:string,cursor?:string|null,limit=24)=>
  api<SourcePage<OcrPhoto>>(base(run)+'/ocr'+query({cursor,limit}))
}
