from clipper import run_project, ConsoleUI

def main():
    ConsoleUI.print_banner()

    try:
        url = ConsoleUI.get_user_url()
        if not url: return
        
        summary_dir, created_clips = run_project(url)
        
        ConsoleUI.show_summary_completion(summary_dir)
        ConsoleUI.show_clips_completion(created_clips)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")
    except Exception as e:
        ConsoleUI.show_error("Terjadi kesalahan fatal", e)

if __name__ == "__main__":
    main()