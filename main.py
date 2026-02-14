from clipper import SummarizeEngine, ConsoleUI, SetupEngine

def main():
    ConsoleUI.print_banner()

    try:
        # Setup awal sistem (Logging, Folder, Dependensi)
        setup = SetupEngine()
        setup.run_system_check()

        url = ConsoleUI.get_user_url()
        if not url: return
        
        app_engine = SummarizeEngine(url)
        result_dir = app_engine.run_summarization()
        
        ConsoleUI.show_completion(result_dir)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")
    except Exception as e:
        ConsoleUI.show_error("Terjadi kesalahan fatal", e)

if __name__ == "__main__":
    main()