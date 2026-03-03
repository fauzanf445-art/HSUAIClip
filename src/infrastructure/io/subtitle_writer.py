import logging
from pathlib import Path
from typing import List, Dict, Any

class AssSubtitleWriter:
    """
    Bertanggung jawab untuk menulis data transkripsi ke dalam format file .ass
    dengan efek karaoke.
    """

    def _format_timestamp(self, seconds: float) -> str:
        """Mengonversi detik ke format timestamp ASS (H:MM:SS.cc)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    def _generate_ass_header(self, play_res_x: int, play_res_y: int) -> str:
        """Menghasilkan header standar V4+ Styles untuk file .ass."""
        base_font_size, base_margin_v, ref_height = 60, 60, 1080
        scale_factor = play_res_y / ref_height
        font_size = int(base_font_size * scale_factor)
        margin_v = int(base_margin_v * scale_factor)

        logging.info(f"   -> Menyesuaikan subtitle untuk resolusi {play_res_y}p. Font: {font_size}px, Margin-V: {margin_v}px")

        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Poppins Bold,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,3,2,0,8,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def write_karaoke_subtitles(
        self, 
        transcription_data: List[Dict[str, Any]], 
        output_path: str, 
        chunk_size: int, 
        play_res_x: int, 
        play_res_y: int
    ):
        """Mengambil data transkripsi terstruktur dan menuliskannya ke file .ass."""
        all_words = [word for segment in transcription_data for word in segment.get('words', [])]
        
        if not all_words:
            logging.warning("Tidak ada kata yang terdeteksi. File subtitle tidak akan dibuat.")
            return

        logging.info(f"📝 Menghasilkan subtitle dari {len(all_words)} kata...")

        output_p = Path(output_path)
        output_p.parent.mkdir(parents=True, exist_ok=True)

        with open(output_p, "w", encoding="utf-8") as f:
            f.write(self._generate_ass_header(play_res_x, play_res_y))

            word_chunks = [all_words[i:i + chunk_size] for i in range(0, len(all_words), chunk_size)]

            for chunk in word_chunks:
                if not chunk: continue

                line_start_time, line_end_time = chunk[0]['start'], chunk[-1]['end']
                start_str, end_str = self._format_timestamp(line_start_time), self._format_timestamp(line_end_time)

                dialogue_parts = ["{\\blur3}"]
                for word_data in chunk:
                    text = word_data['word'].strip()
                    rel_start_ms = int((word_data['start'] - line_start_time) * 1000)
                    
                    jump_dur, pop_dur, settle_dur = 120, 150, 100
                    jump_end_ms = rel_start_ms + jump_dur
                    pop_end_ms = jump_end_ms + pop_dur
                    settle_end_ms = pop_end_ms + settle_dur

                    anim_tags = (f"\\t({rel_start_ms},{jump_end_ms},\\fscy125\\fscx90)"
                                 f"\\t({jump_end_ms},{pop_end_ms},\\fscx115\\fscy115)"
                                 f"\\t({pop_end_ms},{settle_end_ms},\\fscx100\\fscy100)")
                    
                    dialogue_parts.append(f" {{{anim_tags}}}{text}")

                dialogue_text = "".join(dialogue_parts)
                f.write(f"Dialogue: 0,{start_str},{end_str},Karaoke,,0,0,0,,{dialogue_text.strip()}\n")

        logging.info(f"✅ Subtitle disimpan di: {output_path}")